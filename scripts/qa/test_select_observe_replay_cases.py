"""A fair execution order cannot change the full qualification denominator."""

import unittest

import replay_observe_filters as replay
from select_observe_replay_cases import select_cases


class SurfaceSelectionTests(unittest.TestCase):
    def test_attribute_sweep_keeps_same_name_and_type_from_every_family(self):
        cases = [
            {
                "id": f"{family}/{period}/{variant}",
                "period": period,
                "surface": "spans",
                "variant": variant,
                "attributes": ["shared_name"],
                "property_families": [family],
                "blocked": None,
            }
            for family in ("SPAN_ATTRIBUTE", "EVAL", "ANNOTATION")
            for period in ("7D", "30D", "12M")
            for variant in ("string:equals:short", "string:is_not_null")
        ]
        actual = select_cases({"cases": cases}, "attributes", "spans")
        self.assertEqual(set(actual), {case["id"] for case in cases})
        self.assertEqual(len(actual), 18)
        self.assertEqual(
            actual,
            select_cases({"cases": list(reversed(cases))}, "attributes", "spans"),
        )

    def test_span_only_recipe_hash_remains_compatible_with_earlier_selections(self):
        variants = ("string:equals:short", "string:in:short", "string:contains:long")
        chosen = min(
            variants, key=lambda variant: replay.digest([("prop", "string"), variant])
        )
        cases = [
            {
                "id": f"{period}/{variant}",
                "period": period,
                "surface": "spans",
                "variant": variant,
                "attributes": ["prop"],
                "blocked": None,
            }
            for period in ("7D", "30D", "12M")
            for variant in variants
        ]
        self.assertEqual(
            select_cases({"cases": cases}, "attributes", "spans"),
            [f"{period}/{chosen}" for period in ("7D", "30D", "12M")],
        )

    def test_all_surfaces_before_second_recipe_and_all_windows_retained(self):
        cases = []
        for period in ("12M", "30D", "7D"):
            for surface in reversed(replay.SURFACES):
                for variant in ("reported:agent_duration_gt_1", "string:in:short"):
                    cases.append(
                        {
                            "id": f"{period}/{surface}/{variant}",
                            "period": period,
                            "surface": surface,
                            "variant": variant,
                            "attributes": ["company_id"],
                            "blocked": "NO_INPUT"
                            if surface == "dashboard_metric"
                            else None,
                        }
                    )
        plan = {"cases": cases}
        actual = select_cases(plan, "surfaces")
        self.assertEqual(set(actual), {case["id"] for case in cases})
        self.assertEqual(len(actual), len(cases))
        self.assertEqual(
            actual[: len(replay.SURFACES)],
            [f"7D/{surface}/string:in:short" for surface in replay.SURFACES],
        )
        self.assertTrue(actual[-1].startswith("12M/"))
        self.assertEqual(len(plan["cases"]), len(cases))


if __name__ == "__main__":
    unittest.main()
