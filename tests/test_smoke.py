"""Smoke + correctness tests for CHURNLENS. No network, stdlib only."""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from churnlens import TOOL_NAME, TOOL_VERSION, compute_report, parse_events
from churnlens.cli import main
from churnlens.core import ChurnLensError

LEDGER = os.path.join(ROOT, "demos", "01-basic", "subscriptions.csv")

SAMPLE = """date,customer,event,mrr
2026-01-05,acme,new,100
2026-01-09,globex,new,50
2026-02-03,acme,upgrade,150
2026-02-08,globex,churn,0
"""


class TestEngine(unittest.TestCase):
    def test_parse_and_compute_movements(self):
        report = compute_report(parse_events(SAMPLE))
        self.assertEqual(len(report.months), 2)
        jan, feb = report.months

        # January: two new customers totalling 150 MRR.
        self.assertEqual(jan.month, "2026-01")
        self.assertEqual(jan.new_customers, 2)
        self.assertEqual(jan.new_mrr, 150)
        self.assertEqual(jan.mrr_end, 150)
        self.assertEqual(jan.active_end, 2)

        # February: acme +50 expansion, globex churns 50.
        self.assertEqual(feb.mrr_start, 150)
        self.assertEqual(feb.expansion_mrr, 50)
        self.assertEqual(feb.churned_mrr, 50)
        self.assertEqual(feb.churned_customers, 1)
        self.assertEqual(feb.mrr_end, 150)  # 200 - 50
        self.assertEqual(feb.active_end, 1)

        # Feb customer churn = 1 of 2 active at start.
        self.assertAlmostEqual(feb.customer_churn_rate, 0.5)
        # Gross rev churn = churned/start = 50/150.
        self.assertAlmostEqual(feb.gross_revenue_churn, 50 / 150)
        # Net rev churn = (0 + 50 - 50)/150 = 0.
        self.assertAlmostEqual(feb.net_revenue_churn, 0.0)
        # ARPA = 150/1, LTV = ARPA / churn = 150 / 0.5 = 300.
        self.assertAlmostEqual(feb.arpa, 150.0)
        self.assertAlmostEqual(feb.ltv, 300.0)

    def test_report_rollup(self):
        report = compute_report(parse_events(SAMPLE))
        self.assertEqual(report.current_mrr, 150)
        self.assertEqual(report.arr, 1800)
        self.assertEqual(report.active_customers, 1)

    def test_reactivation_counts_as_customer(self):
        text = ("date,customer,event,mrr\n"
                "2026-01-01,a,new,10\n"
                "2026-01-05,a,churn,0\n"
                "2026-02-01,a,reactivation,20\n")
        report = compute_report(parse_events(text))
        feb = report.months[1]
        self.assertEqual(feb.reactivation_mrr, 20)
        self.assertEqual(feb.new_customers, 1)
        self.assertEqual(feb.mrr_end, 20)

    def test_to_dict_is_json_serializable(self):
        report = compute_report(parse_events(SAMPLE))
        json.dumps(report.to_dict())  # must not raise

    def test_bad_event_raises(self):
        with self.assertRaises(ChurnLensError):
            parse_events("date,customer,event,mrr\n2026-01-01,a,bogus,10\n")

    def test_missing_columns_raises(self):
        with self.assertRaises(ChurnLensError):
            parse_events("date,customer,mrr\n2026-01-01,a,10\n")

    def test_bad_date_raises(self):
        with self.assertRaises(ChurnLensError):
            parse_events("date,customer,event,mrr\nnotadate,a,new,10\n")


class TestCLI(unittest.TestCase):
    def test_version_constants(self):
        self.assertEqual(TOOL_NAME, "churnlens")
        self.assertTrue(TOOL_VERSION)

    def test_report_json_exit_zero(self):
        rc = main(["report", LEDGER, "--format", "json"])
        self.assertEqual(rc, 0)

    def test_mrr_table_exit_zero(self):
        rc = main(["mrr", LEDGER])
        self.assertEqual(rc, 0)

    def test_missing_file_nonzero_exit(self):
        rc = main(["report", "does_not_exist_12345.csv"])
        self.assertEqual(rc, 2)

    def test_module_entrypoint_json(self):
        proc = subprocess.run(
            [sys.executable, "-m", "churnlens", "report", LEDGER, "--format", "json"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertIn("months", data)
        self.assertIn("current_mrr", data)


if __name__ == "__main__":
    unittest.main()
