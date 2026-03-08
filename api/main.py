"""FastAPI application — APIs live under the api folder."""
import logging
import sys

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import db_lifespan, get_db
from api.auth import get_current_user
from api.models import User
from api.routes import runs as runs_routes

# Ensure api and src loggers (pipeline, executor, etc.) output to console when running under uvicorn
_root = logging.getLogger()
_root.setLevel(logging.INFO)
if not _root.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    _root.addHandler(_handler)

app = FastAPI(
    title="Agent AI API",
    description="ActionPipe and other APIs.",
    version="0.1.0",
    lifespan=lambda app: db_lifespan(),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_routes.router)


@app.get("/me")
async def me(user: User = Depends(get_current_user)):
    """Return the current authenticated user (from Auth0). Creates/updates user in DB on first login."""
    return {
        "id": str(user.id),
        "org_id": str(user.org_id),
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Check API and database connectivity."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
