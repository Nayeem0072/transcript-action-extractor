"""
LangGraph workflow for the Action Executor pipeline.

  contact_resolver_node  →  mcp_dispatcher_node
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from .nodes import contact_resolver_node, mcp_dispatcher_node
from .state import ExecutorState


def build_executor_graph() -> StateGraph:
    """Construct and compile the two-node executor graph."""
    graph = StateGraph(ExecutorState)

    graph.add_node("contact_resolver", contact_resolver_node)
    graph.add_node("mcp_dispatcher", mcp_dispatcher_node)

    graph.set_entry_point("contact_resolver")
    graph.add_edge("contact_resolver", "mcp_dispatcher")
    graph.add_edge("mcp_dispatcher", END)

    return graph.compile()


def execute_actions(
    normalized_actions: list[dict[str, Any]],
    *,
    dry_run: bool = True,
    contacts_path: str | None = None,
) -> list[dict[str, Any]]:
    """
    Run the full executor pipeline on a list of NormalizedAction dicts.

    Parameters
    ----------
    normalized_actions:
        Output from the normalizer stage (list of dicts matching NormalizedAction schema).
    dry_run:
        When True (default), simulate MCP calls without launching real processes.
    contacts_path:
        Optional path to an alternative contacts.json (useful for testing).

    Returns
    -------
    List of result dicts: {id, tool_type, server, mcp_tool, params, status, response, error}
    """
    graph = build_executor_graph()

    initial_state: ExecutorState = {
        "normalized_actions": normalized_actions,
        "dry_run": dry_run,
    }
    if contacts_path:
        initial_state["contacts_path"] = contacts_path

    final_state = graph.invoke(initial_state)
    return final_state.get("results", [])
