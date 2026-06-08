"""CHURNLENS - Self-hosted SaaS metrics (MRR, churn, LTV) from Stripe exports or CSV.

Own your SaaS metrics. No per-seat fees, no data leaving your machine. Standard
library only.

The engine ingests a subscription-event ledger (CSV) and computes monthly
recurring revenue, customer & revenue churn, ARPA, and LTV using transparent,
auditable math you can verify by hand.
"""
from .core import (
    Event,
    MonthMetrics,
    Report,
    load_events,
    parse_events,
    compute_report,
)

TOOL_NAME = "churnlens"
TOOL_VERSION = "1.0.0"

__all__ = [
    "Event",
    "MonthMetrics",
    "Report",
    "load_events",
    "parse_events",
    "compute_report",
    "TOOL_NAME",
    "TOOL_VERSION",
]
