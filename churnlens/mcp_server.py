"""CHURNLENS MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from churnlens.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-churnlens[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-churnlens[mcp]'")
        return 1
    app = FastMCP("churnlens")

    @app.tool()
    def churnlens_scan(target: str) -> str:
        """Self-hosted SaaS metrics — MRR, churn, LTV from Stripe or CSV. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
