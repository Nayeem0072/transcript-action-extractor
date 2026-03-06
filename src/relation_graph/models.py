"""Pydantic models for the relation graph contact registry."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class Member(BaseModel):
    """An individual member within a group connection."""

    name: str
    email: Optional[str] = None
    slack_handle: Optional[str] = None


class Connection(BaseModel):
    """A named connection (external party, team, or department) for a person."""

    email: Optional[str] = None
    slack_channel: Optional[str] = None
    members: list[Member] = Field(default_factory=list)


class Person(BaseModel):
    """A meeting participant with their contact details and named connections."""

    email: Optional[str] = None
    slack_handle: Optional[str] = None
    notion_workspace: Optional[str] = None
    jira_user: Optional[str] = None
    connections: dict[str, Connection] = Field(default_factory=dict)


class RelationGraph(BaseModel):
    """The full contact registry loaded from contacts.json."""

    people: dict[str, Person] = Field(default_factory=dict)
