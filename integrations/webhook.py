#!/usr/bin/env python3
"""Minimal, dependency-free webhook forwarder for Cognis findings.

Reads JSON findings on stdin and POSTs them to a URL (SIEM/Slack/Jira bridge).
Usage:
    churnlens report LEDGER.csv --format json | python integrations/webhook.py --url URL
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser(
        description="POST JSON findings from stdin to a webhook URL.",
    )
    ap.add_argument("--url", required=True, help="HTTP/HTTPS URL to POST to")
    ap.add_argument(
        "--header", action="append", default=[], help="Extra header: 'Key: Value'",
    )
    args = ap.parse_args()

    # Validate URL scheme before doing any I/O.
    if not args.url.startswith(("http://", "https://")):
        print(
            f"error: --url must start with http:// or https://: {args.url!r}",
            file=sys.stderr,
        )
        return 1

    raw = sys.stdin.read()
    if not raw.strip():
        print("error: stdin is empty — nothing to post", file=sys.stderr)
        return 1

    # Validate that stdin contains well-formed JSON before sending.
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: stdin is not valid JSON: {exc}", file=sys.stderr)
        return 1

    payload = raw.encode("utf-8")
    req = urllib.request.Request(args.url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    for h in args.header:
        k, _, v = h.partition(":")
        key = k.strip()
        val = v.strip()
        if not key:
            print(
                f"error: malformed --header (expected 'Key: Value'): {h!r}",
                file=sys.stderr,
            )
            return 1
        req.add_header(key, val)

    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"posted {len(payload)} bytes -> {r.status}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"webhook error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
