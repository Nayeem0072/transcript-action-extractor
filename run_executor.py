#!/usr/bin/env python3
"""
CLI entry point for the Action Executor (Stage 3).

Usage
-----
  # Dry-run (default) — inspect enriched params + simulated MCP calls
  python run_executor.py output/normalized_output.json

  # Write results to a file
  python run_executor.py output/normalized_output.json output/execution_results.json

  # Live mode — actually calls MCP servers (requires env vars for each service)
  python run_executor.py output/normalized_output.json --live

  # Use a custom contacts file
  python run_executor.py output/normalized_output.json --contacts my_contacts.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute normalized meeting actions via MCP servers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="output/normalized_output.json",
        help="Path to normalized_output.json (default: output/normalized_output.json)",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Optional path to write execution_results.json",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run in live mode (calls real MCP servers). Default is dry-run.",
    )
    parser.add_argument(
        "--contacts",
        default=None,
        metavar="PATH",
        help="Path to a custom contacts.json (overrides src/relation_graph/contacts.json)",
    )
    return parser.parse_args()


def _load_actions(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        logger.error("Input file not found: %s", path)
        sys.exit(1)
    actions = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(actions, list):
        logger.error("Input must be a JSON array of NormalizedAction objects.")
        sys.exit(1)
    return actions


def _print_summary(results: list[dict]) -> None:
    print("\n" + "=" * 70)
    print(f"  EXECUTION SUMMARY  ({len(results)} actions)")
    print("=" * 70)

    status_icons = {
        "success":  "✓",
        "dry_run":  "~",
        "skipped":  "-",
        "error":    "✗",
    }

    for r in results:
        icon = status_icons.get(r["status"], "?")
        server_info = f"{r['server']}/{r['mcp_tool']}" if r["server"] else "no server"
        print(f"  [{icon}] {r['id']:12s}  {r['tool_type']:22s}  {server_info}")
        if r["status"] == "error":
            print(f"           ERROR: {r['error']}")
        elif r["status"] in ("success", "dry_run"):
            params_preview = json.dumps(r["params"], default=str)
            if len(params_preview) > 80:
                params_preview = params_preview[:77] + "..."
            print(f"           params: {params_preview}")

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("-" * 70)
    print("  " + "  |  ".join(f"{k}: {v}" for k, v in counts.items()))
    print("=" * 70 + "\n")


def main() -> None:
    args = parse_args()

    dry_run = not args.live
    mode_label = "DRY RUN" if dry_run else "LIVE"
    logger.info("Action Executor starting — mode: %s", mode_label)

    actions = _load_actions(args.input)
    logger.info("Loaded %d normalized actions from %s", len(actions), args.input)

    from src.action_executor.workflow import execute_actions

    results = execute_actions(
        actions,
        dry_run=dry_run,
        contacts_path=args.contacts,
    )

    _print_summary(results)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(results, indent=2, default=str), encoding="utf-8"
        )
        logger.info("Results written to %s", args.output)


if __name__ == "__main__":
    main()
