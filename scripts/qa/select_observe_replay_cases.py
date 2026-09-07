#!/usr/bin/env python3
"""Select deterministic, fair batches from an immutable full qualification plan.

Selections are execution order, never a replacement acceptance denominator.
Only case IDs are written. Every value and predicate remains in the full plan.
"""

import argparse
from collections import defaultdict
import replay_observe_filters as replay


def select_cases(plan, sweep, surface="traces"):
    buckets = defaultdict(list)
    if sweep == "operators":
        # One stable real property per source/type, every declared operator and
        # value-size variant across all periods. This is a canary ordering;
        # it never replaces the full all-attribute qualification denominator.
        for case in plan["cases"]:
            if case["surface"] != surface or len(case["attributes"]) != 1:
                continue
            if case["variant"].startswith(("reported:", "mixed")):
                continue
            key = (
                tuple(case.get("property_families", ["SPAN_ATTRIBUTE"])),
                case["variant"].split(":", 1)[0],
            )
            buckets[key].append(case)
        selected = []
        for key in sorted(buckets):
            cases = buckets[key]
            eligible = {
                case["attributes"][0]
                for case in cases
                if not case["blocked"] and ":is_" not in case["variant"]
            }
            names = eligible or {case["attributes"][0] for case in cases}
            chosen = min(names, key=replay.digest)
            selected.extend(
                case["id"]
                for case in sorted(
                    (case for case in cases if case["attributes"][0] == chosen),
                    key=lambda case: (
                        case["variant"].endswith(":is_null"),
                        ("12M", "30D", "7D").index(case["period"]),
                        case["variant"],
                    ),
                )
            )
        return selected
    if sweep == "attributes":
        for case in plan["cases"]:
            if case["surface"] != surface or len(case["attributes"]) != 1:
                continue
            variant = case["variant"]
            if variant.startswith(("reported:", "mixed")):
                continue
            # A span attribute and an eval/annotation can share a display name
            # and type. They are different sources and each needs a real-value
            # case; grouping by name/type alone silently drops one family.
            key = (
                tuple(case.get("property_families", ["SPAN_ATTRIBUTE"])),
                case["attributes"][0],
                variant.split(":", 1)[0],
            )
            buckets[key].append(case)
        # Select a real-value positive predicate per observed name/type pair.
        # Missing seeds still get an explicit blocked-value case AND presence.
        # Distribute long/short/IN/contains/range inputs deterministically.
        selected = []
        for period in ("7D", "30D", "12M"):

            def ranking_key(key):
                # Keep existing span-only predeclared selections stable.
                return key[1:] if key[0] == ("SPAN_ATTRIBUTE",) else key

            for key in sorted(buckets, key=lambda key: replay.digest(ranking_key(key))):
                cases = [case for case in buckets[key] if case["period"] == period]
                values = [
                    case
                    for case in cases
                    if any(
                        f":{op}" in case["variant"]
                        for op in (
                            "equals:",
                            "contains:",
                            "in:",
                            "greater_than",
                            "less_than",
                            "value",
                        )
                    )
                ]
                if values:
                    # Same recipe across windows, independent of case-ID hash.
                    chosen = min(
                        values,
                        key=lambda case: replay.digest(
                            [ranking_key(key), case["variant"]]
                        ),
                    )
                    selected.append(chosen["id"])
                presence = [
                    case for case in cases if case["variant"].endswith(":is_not_null")
                ]
                selected.extend(case["id"] for case in presence)
        return selected
    if sweep == "surfaces":
        for case in plan["cases"]:
            if (
                case["variant"]
                in (
                    "reported:agent_duration_gt_1",
                    "reported:interruption_latency_gt_001",
                )
                or (
                    case["attributes"] == ["company_id"]
                    and case["variant"] == "string:in:short"
                )
                or case["variant"]
                in ("mixed_presence:2:0", "mixed_presence:5:0", "mixed_presence:10:0")
            ):
                buckets[(case["period"], case["surface"])].append(case)
        # Exercise one reported recipe across every public surface before
        # spending the run on more recipes on a single surface. Start at 7D
        # and ordinary lists, then graphs/dashboards; do not let three slow
        # 12M dashboards consume the circuit breaker before lists are tried.
        # Every selected case remains present, including blocked inputs.
        recipe_order = (
            "string:in:short",
            "reported:agent_duration_gt_1",
            "reported:interruption_latency_gt_001",
            "mixed_presence:2:0",
            "mixed_presence:5:0",
            "mixed_presence:10:0",
        )
        return [
            case["id"]
            for case in sorted(
                (case for bucket in buckets.values() for case in bucket),
                key=lambda case: (
                    ("7D", "30D", "12M").index(case["period"]),
                    recipe_order.index(case["variant"]),
                    replay.SURFACES.index(case["surface"]),
                    case["id"],
                ),
            )
        ]
    if sweep == "full":
        # Round-robin attributes/recipes, rather than spend the entire first
        # batch on one attribute's many surfaces and claim broad coverage.
        for case in plan["cases"]:
            buckets[tuple(case["attributes"])].append(case)
        selected = []
        ordered = [buckets[key] for key in sorted(buckets, key=replay.digest)]
        for index in range(max(map(len, ordered), default=0)):
            selected.extend(
                bucket[index]["id"] for bucket in ordered if index < len(bucket)
            )
        return selected
    raise replay.ReplayError("UNKNOWN_SWEEP")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument(
        "--sweep",
        choices=("attributes", "operators", "surfaces", "full"),
        required=True,
    )
    parser.add_argument("--surface", default="traces", choices=replay.SURFACES)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    plan = replay.read_json(args.plan)
    if plan["plan_id"] != replay.digest(
        {key: val for key, val in plan.items() if key != "plan_id"}
    ):
        raise replay.ReplayError("PLAN_CHANGED")
    ids = select_cases(plan, args.sweep, args.surface)
    if not ids or len(set(ids)) != len(ids):
        raise replay.ReplayError("EMPTY_OR_DUPLICATE_SELECTION")
    replay.private_write(args.output, ids)
    id_set = set(ids)
    selected = [case for case in plan["cases"] if case["id"] in id_set]
    print(
        replay.canonical(
            {
                "selected": len(ids),
                "blocked": sum(bool(case["blocked"]) for case in selected),
                "attributes": len(
                    {name for case in selected for name in case["attributes"]}
                ),
                "full_plan_cases": len(plan["cases"]),
                "selection_is_not_qualification": True,
            }
        )
    )


if __name__ == "__main__":
    main()
