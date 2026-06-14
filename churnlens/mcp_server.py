"""CHURNLENS MCP server — exposes analyse() as an MCP tool for Cognis.Studio."""
from __future__ import annotations

import json
import sys


def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-churnlens[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print(
            "Install the MCP extra: pip install 'cognis-churnlens[mcp]'",
            file=sys.stderr,
        )
        return 1

    from churnlens.core import ChurnLensError, compute_report, load_events

    app = FastMCP("churnlens")

    @app.tool()
    def churnlens_analyse(ledger_path: str) -> str:
        """Self-hosted SaaS metrics — MRR, churn, LTV from a CSV ledger.

        Args:
            ledger_path: Absolute path to a subscription-event CSV file.

        Returns:
            JSON-encoded report or an error object.
        """
        try:
            events = load_events(ledger_path)
            report = compute_report(events)
            return json.dumps(report.to_dict())
        except FileNotFoundError:
            return json.dumps({"error": f"ledger not found: {ledger_path}"})
        except ChurnLensError as exc:
            return json.dumps({"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"unexpected error: {exc}"})

    app.run()
    return 0
