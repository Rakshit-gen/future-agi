import unittest

from reconcile_observe_query_memory_readonly import recorded_queries, summarize
from replay_observe_filters import ReplayError


class MemoryReconciliationTests(unittest.TestCase):
    def test_recorded_candidate_scope_excludes_reference_and_rejects_mixed_source(self):
        query_id = "observe-local-replay-0123456789ab-1"
        row = {
            "source_sha256": "a" * 64,
            "started_at_utc": "2026-09-05T00:00:00+00:00",
            "queries": [{"query_id": query_id}],
            "independent_reference": {"queries": [{"query_id": "not-candidate"}]},
        }
        self.assertEqual(recorded_queries([row])[0], [query_id])
        with self.assertRaises(ReplayError):
            recorded_queries([row, {**row, "source_sha256": "b" * 64}])
        with self.assertRaises(ReplayError):
            recorded_queries([{**row, "queries": [{"query_id": "arbitrary"}]}])

    def test_missing_and_failed_queries_never_become_complete(self):
        report = summarize(
            ["a", "b", "c"],
            [
                ("a", "QueryFinish", 100, 32, 1, 1, 0),
                ("b", "ExceptionWhileProcessing", 200, 64, 1, 1, 241),
            ],
        )
        self.assertFalse(report["fully_reconciled"])
        self.assertEqual(report["missing_query_ids"], ["c"])
        self.assertEqual(report["query_errors"], 1)
        self.assertEqual(report["max_query_memory_bytes"], 64)
        self.assertTrue(report["memory_includes_failed_queries"])
        self.assertIsNone(summarize(["a"], [])["max_query_memory_bytes"])

    def test_unrequested_or_conflicting_rows_are_rejected(self):
        with self.assertRaises(ReplayError):
            summarize(["a"], [("b", "QueryFinish", 1, 1, 1, 1, 0)])
        with self.assertRaises(ReplayError):
            summarize(
                ["a"],
                [("a", "QueryFinish", 1, memory, 1, 1, 0) for memory in [1, 2]],
            )

    def test_planning_failure_zero_is_not_process_memory_evidence(self):
        report = summarize(
            ["a", "b"],
            [
                ("a", "QueryFinish", 1, 32, 1, 1, 0),
                ("b", "ExceptionBeforeStart", 50, 0, 0, 0, 307),
            ],
        )
        self.assertEqual(report["max_query_memory_bytes"], 32)
        self.assertEqual(report["failed_queries_with_zero_reported_memory"], ["b"])
        self.assertTrue(report["memory_is_reported_query_peak_not_process_peak"])
        self.assertFalse(report["fully_reconciled"])


if __name__ == "__main__":
    unittest.main()
