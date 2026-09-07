#!/usr/bin/env python3
"""Exercise actual local detail SQL on a session from an authorized list case.

SELECT-only, serialized and separately guarded. No fixtures, ORM, HTTP, writes,
or customer content in the report. This is query-layer execution/latency evidence,
not independent correctness, snapshot pagination or full API qualification.
"""

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import replay_observe_filters as replay
from replay_observe_queries_readonly import (
    CandidateQueries,
    ReadOnlyExecutor,
    diagnostic_read_settings,
    initialize_candidate,
    normalize_filters,
    safe_json,
    source_fingerprint,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-read-only", required=True, action="store_true")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--authorized-projects", required=True)
    parser.add_argument("--relational-metadata", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if Path(args.output).exists():
        raise replay.ReplayError("OUTPUT_EXISTS")
    plan = replay.read_json(args.plan)
    if plan["plan_id"] != replay.digest(
        {k: v for k, v in plan.items() if k != "plan_id"}
    ):
        raise replay.ReplayError("PLAN_CHANGED")
    projects = replay.read_json(args.authorized_projects)
    if not isinstance(projects, list) or plan["scope"]["project_id"] not in projects:
        raise replay.ReplayError("PROJECT_NOT_AUTHORIZED")
    cases = [c for c in plan["cases"] if c["id"] == args.case_id]
    if len(cases) != 1 or cases[0]["surface"] != "sessions" or cases[0]["blocked"]:
        raise replay.ReplayError("EXPLICIT_RUNNABLE_SESSION_LIST_CASE_REQUIRED")
    args.host, args.database = "127.0.0.1", "default"
    args.safety_seconds, args.threads, args.read_gib = 60, 2, 8
    before = source_fingerprint()
    initialize_candidate()
    from tracer.services.clickhouse.v2.query_builders.session_detail import (
        build_session_detail_aggregate_query,
        build_session_detail_traces_query,
    )

    reader = ReadOnlyExecutor(args, projects, time.monotonic() + args.safety_seconds)
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": before,
        "plan_id": plan["plan_id"],
        "case_id": args.case_id,
        "qualification": "NOT_QUALIFIED_QUERY_LAYER_ONLY",
        "independent_correctness": False,
        "http_e2e": False,
        "production_configuration_changed": False,
        "omitted_phases": [
            "authorization",
            "PG overlays",
            "eval enrichment",
            "navigation",
            "HTTP",
            "UI",
        ],
        "status": "UNVERIFIED",
    }
    try:
        identity = reader.client.execute(
            "SELECT hostName(), currentDatabase(), version()",
            settings={"readonly": 2, "max_execution_time": 3, "max_threads": 1},
        )[0]
        if identity[:2] != (args.expected_server, args.database):
            raise replay.ReplayError("DATABASE_TARGET_MISMATCH")
        report["server"], report["engine_version"] = identity[0], identity[2]
        candidate = CandidateQueries(args, plan, projects)
        with candidate.metadata.metadata_io():
            payload = candidate.entity_list(
                reader, cases[0], normalize_filters(cases[0]["request"])
            )
        if not payload.get("query_complete") or not payload.get("table"):
            raise replay.ReplayError("NO_PROVEN_POSITIVE_SESSION_SELECTION")
        session_id = str(payload["table"][0]["session_id"])
        report["session_sha256"] = replay.digest(session_id)
        # This dimension has no project column. IDs come only from the authorized
        # candidate result. Closed, parameterized SELECT; never caller SQL.
        remap_sql = """SELECT toString(old_id), toString(new_id)
            FROM trace_session_id_remap FINAL
            WHERE old_id = toUUID(%(sid)s) OR new_id = toUUID(%(sid)s)
               OR new_id IN (SELECT new_id FROM trace_session_id_remap FINAL
                             WHERE old_id = toUUID(%(sid)s))"""
        mark = time.monotonic()
        remaps = reader.client.execute(
            remap_sql,
            {"sid": session_id},
            settings=diagnostic_read_settings(
                {}, remaining_ms=reader.remaining_read_ms(), args=args
            ),
        )
        report["remap_elapsed_ms"] = round((time.monotonic() - mark) * 1000, 2)
        group = tuple(
            sorted({session_id, *(value for pair in remaps for value in pair)})
        )
        report["session_group_size"] = len(group)
        reader.deadline = time.monotonic() + args.safety_seconds
        detail_start = time.monotonic()
        scope = (plan["scope"]["project_id"], group)
        aggregate = reader.execute_ch_query(
            *build_session_detail_aggregate_query(*scope)
        ).data
        first = reader.execute_ch_query(
            *build_session_detail_traces_query(*scope, limit=26, offset=0)
        ).data
        report["first_page_elapsed_ms"] = round(
            (time.monotonic() - detail_start) * 1000, 2
        )
        report["first_page_latency_met"] = report["first_page_elapsed_ms"] < 5000
        visible = first[:25]
        second = []
        if len(first) > 25:
            second = reader.execute_ch_query(
                *build_session_detail_traces_query(*scope, limit=26, offset=25)
            ).data[:25]
        if {r["trace_id"] for r in visible} & {r["trace_id"] for r in second}:
            raise replay.ReplayError("DUPLICATE_TRACE_ACROSS_DETAIL_PAGES")
        report.update(
            status="COMPLETE_UNVERIFIED",
            aggregate_sha256=replay.digest(safe_json(aggregate)),
            first_page_sha256=replay.digest(safe_json(visible)),
            second_page_sha256=replay.digest(safe_json(second)),
            first_page_rows=len(visible),
            second_page_rows=len(second),
            total_traces=aggregate[0]["total_traces"] if aggregate else None,
            second_page_exercised=bool(len(first) > 25),
        )
    except Exception as exc:
        # Error text/SQL may contain customer fields. Only structured codes leave
        # the process; a diagnostic stop is never recorded as an empty success.
        report.update(
            status="ERROR_OR_SAFETY_STOP",
            error_class=type(exc).__name__,
            error_code=getattr(exc, "code", None),
        )
    finally:
        reader.close()
        report["queries"] = reader.calls
        report["source_unchanged"] = source_fingerprint() == before
        if not report["source_unchanged"]:
            report["status"] = "SOURCE_CHANGED"
        replay.private_write(args.output, report)
    print(replay.canonical({k: v for k, v in report.items() if k != "queries"}))
    return 0 if report["status"] == "COMPLETE_UNVERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
