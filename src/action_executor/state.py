"""State definition for the Action Executor pipeline."""
from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class ExecutorState(TypedDict, total=False):
    """Mutable state passed between action executor nodes."""

    normalized_actions: list[dict[str, Any]]
    """NormalizedAction dicts loaded from the normalizer output."""

    enriched_actions: list[dict[str, Any]]
    """Actions after contact resolution — tool_params filled with real addresses."""

    results: list[dict[str, Any]]
    """Execution result per action: {id, tool_type, status, response, error}."""

    dry_run: bool
    """If True, log tool calls but do not connect to live MCP servers."""

    contacts_path: Optional[str]
    """Optional override path to contacts.json (used in tests)."""
