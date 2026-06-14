"""CHURNLENS command-line interface.

Usage:
    churnlens report LEDGER.csv [--format table|json] [--currency USD]
    churnlens mrr    LEDGER.csv [--format table|json]   # latest-month summary
    churnlens --version
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import ChurnLensError, compute_report, load_events


def _pct(x: float) -> str:
    return f"{x * 100:6.2f}%"


def _money(x: float, cur: str) -> str:
    return f"{cur} {x:,.2f}"


def _render_report_table(report) -> str:
    cur = report.currency
    lines = []
    lines.append("=" * 72)
    lines.append(f"CHURNLENS report  ({cur})")
    lines.append("=" * 72)
    lines.append(f"Current MRR      : {_money(report.current_mrr, cur)}")
    lines.append(f"ARR (run-rate)   : {_money(report.arr, cur)}")
    lines.append(f"Active customers : {report.active_customers}")
    lines.append(f"Avg cust. churn  : {_pct(report.avg_customer_churn)}")
    lines.append("-" * 72)
    hdr = (f"{'Month':<8}{'MRR end':>12}{'Net new':>11}"
           f"{'Cust':>6}{'C.churn':>9}{'NetRevChn':>11}{'LTV':>10}")
    lines.append(hdr)
    lines.append("-" * 72)
    for m in report.months:
        lines.append(
            f"{m.month:<8}"
            f"{m.mrr_end:>12,.0f}"
            f"{m.net_new_mrr:>11,.0f}"
            f"{m.active_end:>6}"
            f"{m.customer_churn_rate * 100:>8.2f}%"
            f"{m.net_revenue_churn * 100:>10.2f}%"
            f"{m.ltv:>10,.0f}"
        )
    lines.append("=" * 72)
    return "\n".join(lines)


def _render_mrr_table(report) -> str:
    cur = report.currency
    m = report.months[-1]
    lines = [
        f"CHURNLENS - latest month: {m.month}",
        "-" * 40,
        f"MRR start        : {_money(m.mrr_start, cur)}",
        f"  + new          : {_money(m.new_mrr, cur)}",
        f"  + expansion    : {_money(m.expansion_mrr, cur)}",
        f"  + reactivation : {_money(m.reactivation_mrr, cur)}",
        f"  - contraction  : {_money(m.contraction_mrr, cur)}",
        f"  - churned      : {_money(m.churned_mrr, cur)}",
        f"MRR end          : {_money(m.mrr_end, cur)}",
        f"Net new MRR      : {_money(m.net_new_mrr, cur)}",
        f"ARPA             : {_money(m.arpa, cur)}",
        f"Gross rev churn  : {_pct(m.gross_revenue_churn)}",
        f"Net rev churn    : {_pct(m.net_revenue_churn)}",
        f"Customer churn   : {_pct(m.customer_churn_rate)}",
    ]
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Self-hosted SaaS metrics: MRR, churn, LTV from a CSV ledger.",
    )
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    rep = sub.add_parser("report", help="full per-month metrics report")
    rep.add_argument("ledger", help="path to subscription-event CSV")
    rep.add_argument("--format", choices=["table", "json"], default="table")
    rep.add_argument("--currency", default="USD")

    mrr = sub.add_parser("mrr", help="latest-month MRR movement summary")
    mrr.add_argument("ledger", help="path to subscription-event CSV")
    mrr.add_argument("--format", choices=["table", "json"], default="table")
    mrr.add_argument("--currency", default="USD")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        events = load_events(args.ledger)
        report = compute_report(events, currency=args.currency)
    except FileNotFoundError:
        print(f"error: ledger not found: {args.ledger}", file=sys.stderr)
        return 2
    except PermissionError:
        print(f"error: permission denied reading: {args.ledger}", file=sys.stderr)
        return 2
    except UnicodeDecodeError as exc:
        print(f"error: cannot decode ledger (expected UTF-8): {exc}", file=sys.stderr)
        return 1
    except ChurnLensError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"error: unexpected error: {exc}", file=sys.stderr)
        return 1

    if args.command == "report":
        if args.format == "json":
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(_render_report_table(report))
    elif args.command == "mrr":
        if args.format == "json":
            print(json.dumps(report.months[-1].to_dict(), indent=2))
        else:
            print(_render_mrr_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
