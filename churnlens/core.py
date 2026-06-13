"""CHURNLENS engine.

Input model
-----------
A CSV ledger of subscription events, one row per state change. Columns:

    date        ISO date (YYYY-MM-DD) the event took effect
    customer    stable customer id
    event       one of: new | upgrade | downgrade | churn | reactivation
    mrr         the customer's NEW monthly recurring revenue *after* this event
                (in dollars; churn rows should be 0)

This "snapshot-after" model is exactly what you get from a Stripe subscription
export reduced to MRR, and it makes the math unambiguous: at any event we know
the customer's prior MRR (from their last event) and their new MRR.

Metrics (computed per calendar month spanning the data)
-------------------------------------------------------
* MRR at end of month, and net new MRR for the month
* New / expansion / contraction / churned / reactivation MRR movement
* Active customer count, new & churned customer counts
* Customer churn rate  = churned customers / active at month start
* Gross revenue churn   = (contraction + churned MRR) / MRR at month start
* Net revenue churn     = (contraction + churned - expansion) / MRR at start
* ARPA                  = MRR / active customers
* LTV                   = ARPA / customer-churn-rate (avg lifetime value)

All figures are rounded to cents/whole numbers only at the reporting boundary.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Dict, List, Iterable

VALID_EVENTS = {"new", "upgrade", "downgrade", "churn", "reactivation"}


class ChurnLensError(Exception):
    """Raised on malformed input."""


@dataclass
class Event:
    date: date
    customer: str
    event: str
    mrr: float  # MRR after the event

    @property
    def month(self) -> str:
        return f"{self.date.year:04d}-{self.date.month:02d}"


@dataclass
class MonthMetrics:
    month: str
    mrr_start: float = 0.0
    mrr_end: float = 0.0
    new_mrr: float = 0.0
    expansion_mrr: float = 0.0
    contraction_mrr: float = 0.0
    churned_mrr: float = 0.0
    reactivation_mrr: float = 0.0
    active_start: int = 0
    active_end: int = 0
    new_customers: int = 0
    churned_customers: int = 0

    @property
    def net_new_mrr(self) -> float:
        return self.mrr_end - self.mrr_start

    @property
    def customer_churn_rate(self) -> float:
        if self.active_start == 0:
            return 0.0
        return self.churned_customers / self.active_start

    @property
    def gross_revenue_churn(self) -> float:
        if self.mrr_start == 0:
            return 0.0
        return (self.contraction_mrr + self.churned_mrr) / self.mrr_start

    @property
    def net_revenue_churn(self) -> float:
        if self.mrr_start == 0:
            return 0.0
        net = self.contraction_mrr + self.churned_mrr - self.expansion_mrr
        return net / self.mrr_start

    @property
    def arpa(self) -> float:
        if self.active_end == 0:
            return 0.0
        return self.mrr_end / self.active_end

    @property
    def ltv(self) -> float:
        rate = self.customer_churn_rate
        if rate <= 0:
            return 0.0
        return self.arpa / rate

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(
            net_new_mrr=round(self.net_new_mrr, 2),
            customer_churn_rate=round(self.customer_churn_rate, 6),
            gross_revenue_churn=round(self.gross_revenue_churn, 6),
            net_revenue_churn=round(self.net_revenue_churn, 6),
            arpa=round(self.arpa, 2),
            ltv=round(self.ltv, 2),
        )
        for k in ("mrr_start", "mrr_end", "new_mrr", "expansion_mrr",
                  "contraction_mrr", "churned_mrr", "reactivation_mrr"):
            d[k] = round(d[k], 2)
        return d


@dataclass
class Report:
    months: List[MonthMetrics] = field(default_factory=list)
    currency: str = "USD"

    @property
    def current_mrr(self) -> float:
        return self.months[-1].mrr_end if self.months else 0.0

    @property
    def arr(self) -> float:
        return self.current_mrr * 12

    @property
    def active_customers(self) -> int:
        return self.months[-1].active_end if self.months else 0

    @property
    def avg_customer_churn(self) -> float:
        rates = [m.customer_churn_rate for m in self.months if m.active_start]
        return sum(rates) / len(rates) if rates else 0.0

    def to_dict(self) -> dict:
        return {
            "currency": self.currency,
            "current_mrr": round(self.current_mrr, 2),
            "arr": round(self.arr, 2),
            "active_customers": self.active_customers,
            "avg_customer_churn_rate": round(self.avg_customer_churn, 6),
            "months": [m.to_dict() for m in self.months],
        }


def parse_events(text: str) -> List[Event]:
    """Parse CSV text into a sorted list of Events."""
    reader = csv.DictReader(io.StringIO(text))
    required = {"date", "customer", "event", "mrr"}
    if reader.fieldnames is None:
        raise ChurnLensError("empty input: no CSV header found")
    missing = required - {(f or "").strip() for f in reader.fieldnames}
    if missing:
        raise ChurnLensError(f"missing required columns: {sorted(missing)}")

    events: List[Event] = []
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        try:
            d = date.fromisoformat(row["date"].strip())
        except (ValueError, AttributeError) as exc:
            raise ChurnLensError(f"row {i}: bad date {row.get('date')!r}: {exc}")
        ev = (row["event"] or "").strip().lower()
        if ev not in VALID_EVENTS:
            raise ChurnLensError(
                f"row {i}: invalid event {ev!r}; expected one of {sorted(VALID_EVENTS)}"
            )
        cust = (row["customer"] or "").strip()
        if not cust:
            raise ChurnLensError(f"row {i}: empty customer id")
        try:
            mrr = float(row["mrr"])
        except (ValueError, TypeError) as exc:
            raise ChurnLensError(f"row {i}: bad mrr {row.get('mrr')!r}: {exc}")
        if mrr < 0:
            raise ChurnLensError(f"row {i}: negative mrr {mrr}")
        events.append(Event(d, cust, ev, mrr))

    if not events:
        raise ChurnLensError("no event rows found")
    # Stable chronological sort; ties keep file order (csv import order).
    events.sort(key=lambda e: e.date)
    return events


def load_events(path: str) -> List[Event]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return parse_events(fh.read())


def _months_between(first: str, last: str) -> List[str]:
    fy, fm = int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    out = []
    y, m = fy, fm
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def compute_report(events: Iterable[Event], currency: str = "USD") -> Report:
    """Fold the event ledger into per-month metrics.

    Tracks each customer's current MRR. Each event's movement is the delta
    between the customer's prior MRR and the snapshot MRR carried on the event.
    """
    events = list(events)
    if not events:
        raise ChurnLensError("no events to compute")

    all_months = _months_between(events[0].month, events[-1].month)
    by_month: Dict[str, List[Event]] = {m: [] for m in all_months}
    for e in events:
        by_month[e.month].append(e)

    customer_mrr: Dict[str, float] = {}  # current MRR per active customer
    report = Report(currency=currency)

    for month in all_months:
        mm = MonthMetrics(month=month)
        mm.mrr_start = round(sum(customer_mrr.values()), 10)
        mm.active_start = len(customer_mrr)

        for e in by_month[month]:
            prior = customer_mrr.get(e.customer, 0.0)
            new = e.mrr
            delta = new - prior
            was_active = e.customer in customer_mrr

            if e.event == "new":
                mm.new_mrr += new
                mm.new_customers += 1
                customer_mrr[e.customer] = new
            elif e.event == "reactivation":
                mm.reactivation_mrr += new
                if not was_active:
                    mm.new_customers += 1
                customer_mrr[e.customer] = new
            elif e.event == "churn":
                mm.churned_mrr += prior
                mm.churned_customers += 1
                customer_mrr.pop(e.customer, None)
            elif e.event == "upgrade":
                if delta >= 0:
                    mm.expansion_mrr += delta
                else:
                    mm.contraction_mrr += -delta
                customer_mrr[e.customer] = new
            elif e.event == "downgrade":
                if delta <= 0:
                    mm.contraction_mrr += -delta
                else:
                    mm.expansion_mrr += delta
                customer_mrr[e.customer] = new

        mm.mrr_end = round(sum(customer_mrr.values()), 10)
        mm.active_end = len(customer_mrr)
        report.months.append(mm)

    return report
