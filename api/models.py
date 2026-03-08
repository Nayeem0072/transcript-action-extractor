"""SQLAlchemy models for organizations, users, tokens, and org-level contacts."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base for all models."""
    pass


class Organization(Base):
    """An organization; users belong to one org and share its contacts."""
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    actionpipe_org_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default="test org")
    actionpipe_org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.UUID("8675108e-fc97-47ea-9838-a1a3f3fad3f4"), nullable=False)

    users: Mapped[list["User"]] = relationship("User", back_populates="organization")
    org_contact: Mapped["OrgContact | None"] = relationship("OrgContact", back_populates="organization", uselist=False)


class User(Base):
    """A user belonging to an organization; has login identity and linked tokens."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    auth0_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)  # Auth0 "sub" claim
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    picture: Mapped[str | None] = mapped_column(String(512), nullable=True)  # Auth0 profile picture URL
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)  # for login; set when auth is added
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="users")
    tokens: Mapped[list["UserToken"]] = relationship("UserToken", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_user_org_email"),)


class UserToken(Base):
    """Per-user access token for a service (Jira, Slack, Notion, etc.)."""
    __tablename__ = "user_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    service: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. jira, slack, notion
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="tokens")

    __table_args__ = (UniqueConstraint("user_id", "service", name="uq_user_token_service"),)


class OrgContact(Base):
    """One JSONB contacts graph per organization (same shape as contacts.json)."""
    __tablename__ = "org_contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    contacts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="org_contact")
