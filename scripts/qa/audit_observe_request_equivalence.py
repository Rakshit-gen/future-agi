#!/usr/bin/env python3
"""Offline exact-request workload audit; never executes or qualifies a case.

Shared source code or a common SQL builder does not prove equal workloads.
Keep the entire request, scope, declared window and property families in the
identity. Do not coerce types, reorder lists, normalize embedded JSON strings,
drop page sizes or strip user filters to create more equivalences.
"""

import argparse
from collections import Counter
import re

import replay_observe_filters as replay
from replay_observe_queries_readonly import source_fingerprint


def audit(plan, source_sha256):
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise replay.ReplayError("SOURCE_FINGERPRINT_REQUIRED")
    if not isinstance(plan.get("scope"), dict) or not plan["scope"]:
        raise replay.ReplayError("PLAN_SCOPE_REQUIRED")
    if not isinstance(plan.get("cases"), list):
        raise replay.ReplayError("PLAN_CASES_REQUIRED")
    seen, groups, blocked = set(), {}, []
    for case in plan["cases"]:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise replay.ReplayError("CASE_IDS_MUST_BE_UNIQUE")
        seen.add(case_id)
        if case.get("blocked"):
            blocked.append(case_id)
            continue
        request = case.get("request")
        if not isinstance(request, dict) or not request:
            raise replay.ReplayError("CASE_REQUEST_REQUIRED")
        target = case.get("target_ms")
        if type(target) not in (float, int) or target <= 0:
            raise replay.ReplayError("POSITIVE_TARGET_REQUIRED")
        identity = {
            "scope": plan["scope"],
            "request": request,
            "window": case.get("window"),
            "property_families": case.get("property_families"),
        }
        key = replay.digest(identity)
        group = groups.setdefault(
            key,
            {
                "request_sha256": key,
                "representative_case_id": case_id,
                "case_ids": [],
                "surfaces": [],
                "strictest_target_ms": target,
            },
        )
        group["case_ids"].append(case_id)
        if case["surface"] not in group["surfaces"]:
            group["surfaces"].append(case["surface"])
        group["strictest_target_ms"] = min(group["strictest_target_ms"], target)
    unblocked = len(seen) - len(blocked)
    records = list(groups.values())
    return {
        "schema": "observe-exact-request-audit.v1",
        "plan_id": plan.get("plan_id"),
        "plan_content_sha256": replay.digest(plan),
        "source_sha256": source_sha256,
        "scope_sha256": replay.digest(plan["scope"]),
        "total_cases": len(seen),
        "blocked_input_cases": len(blocked),
        "unblocked_cases": unblocked,
        "exact_request_groups": len(records),
        "potential_duplicate_requests": unblocked - len(records),
        "group_size_histogram": dict(
            sorted(Counter(len(g["case_ids"]) for g in records).items())
        ),
        "cross_surface_groups": sum(len(g["surfaces"]) > 1 for g in records),
        "queries_executed": 0,
        "qualification_status": "NOT_EXECUTED",
        "results_may_be_reused_automatically": False,
        "limitations": [
            "Request identity is not proof of candidate adapter equivalence.",
            "No timing, correctness, full-row, pagination or UI pass is conferred.",
            "Shared backend evidence cannot replace each feature integration check.",
            "Blocked-input cases are retained, not silently removed from coverage.",
            "No ETA is inferred from group counts.",
        ],
        "blocked_case_ids": blocked,
        "groups": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    before = source_fingerprint()
    result = audit(replay.read_json(args.plan), before)
    if source_fingerprint() != before:
        raise replay.ReplayError("SOURCE_CHANGED_DURING_AUDIT")
    replay.private_write(args.output, result)
    print(
        replay.canonical(
            {k: v for k, v in result.items() if k not in {"groups", "blocked_case_ids"}}
        )
    )


if __name__ == "__main__":
    main()
