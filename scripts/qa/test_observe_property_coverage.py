"""Coverage accounting and source identity tests, not production evidence."""

import copy
import json
import unittest

import replay_observe_filters as replay
import replay_observe_queries_readonly as queries
from discover_observe_relational_inputs import REMOTE_PROGRAM
from select_observe_replay_cases import select_cases
from test_replay_observe_filters import ATTR, SCOPE, fixture_plan


def family_plan():
    return replay.make_plan(
        {
            "scope": SCOPE,
            "attributes": [ATTR],
            "properties": [
                {
                    "name": "company_id",
                    "column_id": column,
                    "col_type": family,
                    "source": "traces",
                    "observed_types": ["number"],
                    "resolved_type": "number",
                    "seeds": [{"type": "number", "value": 2}],
                }
                for family, column in (
                    ("SYSTEM_METRIC", "latency"),
                    ("EVAL_METRIC", "11111111-1111-4111-8111-111111111111"),
                    ("ANNOTATION", "22222222-2222-4222-8222-222222222222"),
                )
            ],
        },
        replay.utc("2026-09-05T00:00:00Z"),
        (
            "traces",
            "users_project",
            "trace_graph",
            "dashboard_filter",
            "dashboard_metric",
        ),
        2,
    )


class PropertyCoverageTests(unittest.TestCase):
    def test_all_families_remain_distinct_on_wire_and_in_report(self):
        plan = family_plan()
        self.assertEqual(plan["attribute_count"], 1)
        self.assertEqual(plan["property_count"], 4)
        for family in replay.REQUIRED_PROPERTY_FAMILIES:
            self.assertEqual(plan["property_family_inventory"][family]["properties"], 1)
        for case in plan["cases"]:
            if case["blocked"] or len(case["attributes"]) != 1:
                continue
            request = case["request"]
            filters = (
                request["body"]["filters"]
                if request["body"]
                else json.loads(request["params"]["filters"])
            )
            leaf = filters[1]
            self.assertEqual(
                leaf["filter_config"]["col_type"], case["property_families"][0]
            )
            self.assertNotIn("EVAL_METRIC:", leaf["column_id"])
            if case["property_families"] != ["SPAN_ATTRIBUTE"] and not request["body"]:
                self.assertEqual(json.loads(request["params"]["attribute_keys"]), [])

    def test_absent_families_cannot_disappear_from_coverage(self):
        plan = fixture_plan()
        report = queries.qualification_summary(plan, [], "current")
        self.assertEqual(
            set(report["by_property_family"]), set(replay.REQUIRED_PROPERTY_FAMILIES)
        )
        self.assertEqual(report["by_property_family"]["ANNOTATION"], {})
        self.assertFalse(report["property_family_coverage_complete"])
        self.assertEqual(report["qualification"], "NOT_QUALIFIED")

    def test_operator_counts_keep_untested_negative_and_range_cases(self):
        plan = family_plan()
        report = queries.qualification_summary(plan, [], "current")
        for family in replay.REQUIRED_PROPERTY_FAMILIES:
            key = (
                family
                + "/"
                + (
                    "text/not_in"
                    if family == "SPAN_ATTRIBUTE"
                    else "number/not_between"
                )
            )
            counts = report["by_property_type_operator"][key]
            self.assertGreater(counts["UNTESTED"], 0)
            self.assertEqual(counts.get("executed", 0), 0)
        self.assertNotIn(
            "SYSTEM_METRIC/datetime/between", report["by_property_type_operator"]
        )

    def test_mixed_recipes_include_distinct_property_families(self):
        plan = family_plan()
        mixed = [
            case for case in plan["cases"] if case["variant"].startswith("mixed:2:")
        ]
        self.assertTrue(mixed)
        self.assertTrue(any(len(case["property_families"]) == 2 for case in mixed))

    def test_unimplemented_source_projection_is_explicit_not_custom_coercion(self):
        plan = family_plan()
        cases = [
            case
            for case in plan["cases"]
            if case["surface"] == "dashboard_metric"
            and case["property_families"] == ["EVAL_METRIC"]
        ]
        self.assertTrue(cases)
        self.assertTrue(
            all(
                case["blocked"]
                == "SOURCE_SPECIFIC_DASHBOARD_PROJECTION_NOT_IMPLEMENTED"
                for case in cases
            )
        )

    def test_unknown_family_never_defaults_to_span_attribute(self):
        with self.assertRaisesRegex(replay.ReplayError, "UNKNOWN_PROPERTY_FAMILY"):
            replay.raw_leaf({**ATTR, "col_type": "unrecognized"}, "number", "equals", 1)

    def test_declared_source_and_property_identity_are_preserved(self):
        leaf = replay.raw_leaf(
            {
                "name": "same",
                "column_id": "real-label",
                "property_id": "annotation:real-label",
                "source": "sessions",
                "col_type": "ANNOTATION",
            },
            "number",
            "equals",
            2,
        )
        self.assertEqual(leaf["column_id"], "real-label")
        self.assertEqual(leaf["source"], "sessions")
        self.assertEqual(leaf["property_id"], "annotation:real-label")


class SweepTests(unittest.TestCase):
    def test_operator_canary_keeps_every_operator_and_period_per_type(self):
        plan = family_plan()
        selected_ids = select_cases(plan, "operators")
        selected = [case for case in plan["cases"] if case["id"] in selected_ids]
        self.assertEqual(selected_ids, select_cases(copy.deepcopy(plan), "operators"))
        self.assertEqual(len(selected_ids), len(set(selected_ids)))
        for case in selected:
            self.assertEqual(case["surface"], "traces")
            self.assertEqual(len(case["attributes"]), 1)
        for family in replay.REQUIRED_PROPERTY_FAMILIES:
            cases = [case for case in selected if case["property_families"] == [family]]
            self.assertEqual({case["period"] for case in cases}, {"7D", "30D", "12M"})
            for period in ("7D", "30D", "12M"):
                got = {case["variant"] for case in cases if case["period"] == period}
                self.assertEqual(got, {case["variant"] for case in cases})

    def test_every_name_type_pair_and_window_has_value_and_presence_selection(self):
        plan = fixture_plan()
        ids = select_cases(plan, "attributes")
        self.assertEqual(len(ids), 2 * 2 * 3)
        self.assertEqual(len(set(ids)), len(ids))
        by_id = {case["id"]: case for case in plan["cases"]}
        self.assertEqual({by_id[i]["period"] for i in ids}, {"7D", "30D", "12M"})
        self.assertEqual(ids, select_cases(copy.deepcopy(plan), "attributes"))

    def test_missing_value_still_has_a_declared_blocked_case(self):
        plan = fixture_plan(attributes=[{**ATTR, "seeds": []}])
        ids = select_cases(plan, "attributes")
        by_id = {case["id"]: case for case in plan["cases"]}
        self.assertEqual(sum(bool(by_id[i]["blocked"]) for i in ids), 6)

    def test_full_selection_never_drops_or_duplicates_case(self):
        plan = family_plan()
        ids = select_cases(plan, "full")
        self.assertEqual(set(ids), {case["id"] for case in plan["cases"]})
        self.assertEqual(len(ids), len(plan["cases"]))


class RelationalReadOnlyTests(unittest.TestCase):
    def test_discovery_has_no_django_startup_or_mutation(self):
        compile(REMOTE_PROGRAM, "<metadata-discovery>", "exec")
        self.assertIn("c.read_only = True", REMOTE_PROGRAM)
        self.assertIn("transaction_read_only", REMOTE_PROGRAM)
        self.assertIn("c.rollback()", REMOTE_PROGRAM)
        self.assertIn("PROJECT_AUTHORIZATION_MISMATCH", REMOTE_PROGRAM)
        self.assertIn("s.tracer_project_id", REMOTE_PROGRAM)
        self.assertNotIn("s.project_id", REMOTE_PROGRAM)
        for forbidden in (
            "django.setup",
            "c.commit",
            "INSERT ",
            "UPDATE ",
            "DELETE ",
            "ALTER ",
            "CREATE ",
        ):
            self.assertNotIn(forbidden, REMOTE_PROGRAM)


if __name__ == "__main__":
    unittest.main()
