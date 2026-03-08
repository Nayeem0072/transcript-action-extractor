"""Auth0 JWT verification and user get-or-create for FastAPI."""
import logging
import os
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_db
from api.models import Organization, User

logger = logging.getLogger(__name__)

HTTP_BEARER = HTTPBearer(auto_error=False)

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "").rstrip("/").replace("https://", "").replace("http://", "")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "")
AUTH0_ISSUER = f"https://{AUTH0_DOMAIN}/" if AUTH0_DOMAIN else ""

# In-memory cache of JWKS (key by kid)
_jwks_cache: dict[str, dict] = {}
_jwks_cache_issuer: str | None = None


def _get_jwks() -> dict:
    """Fetch Auth0 JWKS (cached)."""
    global _jwks_cache, _jwks_cache_issuer
    if not AUTH0_DOMAIN:
        return {}
    if _jwks_cache_issuer != AUTH0_ISSUER:
        _jwks_cache.clear()
        _jwks_cache_issuer = AUTH0_ISSUER
    if _jwks_cache:
        return _jwks_cache
    url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        for key in data.get("keys", []):
            kid = key.get("kid")
            if kid:
                _jwks_cache[kid] = key
        return _jwks_cache
    except Exception as e:
        logger.warning("Failed to fetch Auth0 JWKS: %s", e)
        return _jwks_cache


def verify_auth0_token(token: str) -> dict:
    """
    Verify Auth0 JWT and return payload (sub, email, name, picture).
    Raises HTTPException if invalid or Auth0 not configured.
    """
    if not AUTH0_DOMAIN or not AUTH0_AUDIENCE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth0 is not configured (AUTH0_DOMAIN / AUTH0_AUDIENCE)",
        )
    jwks = _get_jwks()
    if not jwks:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load Auth0 signing keys",
        )
    try:
        unverified = jwt.get_unverified_header(token)
        kid = unverified.get("kid")
        if not kid or kid not in jwks:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token key id")
        key = jwt.algorithms.RSAAlgorithm.from_jwk(jwks[kid])
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=AUTH0_AUDIENCE,
            issuer=AUTH0_ISSUER,
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception as e:
        logger.warning("Token verification error: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _is_placeholder_name(name: str | None) -> bool:
    """True if name is missing or looks like Auth0 sub/placeholder (e.g. google-oauth2|123@auth0.user)."""
    if not name or not (name := name.strip()):
        return True
    return "@auth0.user" in name or "|" in name


def _is_placeholder_email(email: str | None) -> bool:
    """True if email is missing or the placeholder we use for missing email."""
    if not email or not email.strip():
        return True
    return email.strip().endswith("@auth0.user")


async def _fetch_auth0_userinfo(access_token: str) -> dict | None:
    """Fetch user profile from Auth0 /userinfo (email, name, picture). Returns None on failure."""
    if not AUTH0_DOMAIN:
        return None
    url = f"https://{AUTH0_DOMAIN}/userinfo"
    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("Auth0 userinfo fetch failed: %s", e)
        return None


async def get_or_create_user(db: AsyncSession, payload: dict) -> User:
    """
    Find user by auth0_id (sub); if not found, create Organization and User.
    Update name/email/picture if changed.
    Payload can be from JWT and/or Auth0 /userinfo (email, name, picture).
    """
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub")
    email = (payload.get("email") or "").strip() or (payload.get("https://your-app/email") or "").strip()
    name = (payload.get("name") or payload.get("nickname") or "").strip() or None
    if _is_placeholder_name(name):
        name = None
        # Prefer given_name + family_name from userinfo when name was placeholder
        given = (payload.get("given_name") or "").strip()
        family = (payload.get("family_name") or "").strip()
        if given or family:
            name = f"{given} {family}".strip() or None
    picture = (payload.get("picture") or "").strip() or None
    if _is_placeholder_email(email):
        email = f"{sub}@auth0.user"  # fallback only if still missing or placeholder

    result = await db.execute(select(User).where(User.auth0_id == sub))
    user = result.scalars().first()
    if user:
        changed = False
        if user.name != name:
            user.name = name
            changed = True
        if user.email != email:
            user.email = email
            changed = True
        if user.picture != picture:
            user.picture = picture
            changed = True
        if changed:
            await db.flush()
        return user

    # Create org and user — use a human-readable org name when possible
    if name:
        org_name = name
    elif email and not _is_placeholder_email(email):
        local = email.split("@")[0]
        org_name = local if "|" not in local else "Personal"
    else:
        org_name = "Personal"
    org = Organization(name=org_name)
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id,
        auth0_id=sub,
        email=email,
        name=name,
        picture=picture,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    logger.info("Created user from Auth0: auth0_id=%s email=%s", sub, email)
    return user


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(HTTP_BEARER)],
) -> User:
    """
    FastAPI dependency: require Authorization Bearer token, verify with Auth0, return DB user.
    Call this on any route that requires login; user is created/updated on first use.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    payload = verify_auth0_token(token)
    # Access tokens for an API often omit email/name or have placeholder; fetch from Auth0 /userinfo if needed
    email = (payload.get("email") or "").strip()
    name = (payload.get("name") or payload.get("nickname") or "").strip() or None
    if _is_placeholder_email(email) or _is_placeholder_name(name):
        userinfo = await _fetch_auth0_userinfo(token)
        if userinfo:
            payload = {**payload, **userinfo}
    user = await get_or_create_user(db, payload)
    return user
