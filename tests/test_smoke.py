"""Smoke + correctness tests for CHURNLENS. No network, stdlib only."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from churnlens import TOOL_NAME, TOOL_VERSION, compute_report, parse_events  # noqa: E402
from churnlens.cli import main  # noqa: E402
from churnlens.core import ChurnLensError  # noqa: E402

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

    def test_header_only_raises(self):
        """A CSV with a valid header but zero data rows must raise ChurnLensError."""
        with self.assertRaises(ChurnLensError):
            parse_events("date,customer,event,mrr\n")

    def test_empty_string_raises(self):
        """Completely empty input must raise ChurnLensError (no header)."""
        with self.assertRaises(ChurnLensError):
            parse_events("")

    def test_negative_mrr_raises(self):
        """MRR values below zero must be rejected."""
        with self.assertRaises(ChurnLensError):
            parse_events("date,customer,event,mrr\n2026-01-01,a,new,-5\n")

    def test_bad_mrr_type_raises(self):
        """Non-numeric MRR must produce a clear ChurnLensError, not a ValueError."""
        with self.assertRaises(ChurnLensError):
            parse_events("date,customer,event,mrr\n2026-01-01,a,new,notanumber\n")

    def test_empty_customer_raises(self):
        """Blank customer ID must raise ChurnLensError."""
        with self.assertRaises(ChurnLensError):
            parse_events("date,customer,event,mrr\n2026-01-01,,new,50\n")


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

    def test_malformed_csv_returns_exit_1(self):
        """A CSV with a bad event value must exit 1 (not crash)."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8",
        ) as f:
            f.write("date,customer,event,mrr\n2026-01-01,x,unknown_event,100\n")
            bad_path = f.name
        try:
            rc = main(["report", bad_path])
            self.assertEqual(rc, 1)
        finally:
            os.unlink(bad_path)

    def test_header_only_csv_returns_exit_1(self):
        """A CSV that has a header but no rows must exit 1 with a clear message."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8",
        ) as f:
            f.write("date,customer,event,mrr\n")
            empty_path = f.name
        try:
            rc = main(["report", empty_path])
            self.assertEqual(rc, 1)
        finally:
            os.unlink(empty_path)

    def test_mcp_server_imports_cleanly(self):
        """mcp_server must import without raising an ImportError."""
        import importlib
        import churnlens.mcp_server  # noqa: F401
        mod = importlib.import_module("churnlens.mcp_server")
        self.assertTrue(callable(mod.serve))


if __name__ == "__main__":
    unittest.main()
