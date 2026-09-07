#!/usr/bin/env python3
"""Actual annotation membership compiler over literal latest-state fixtures.

No production table reads or writes. Supplementary semantics evidence only.
"""

import argparse
import os
from datetime import UTC, datetime

import replay_observe_filters as replay
from replay_observe_queries_readonly import initialize_candidate, source_fingerprint

PROJECT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
LABEL = "33333333-3333-4333-8333-333333333333"
TRACES = [f"44444444-4444-4444-8444-{i:012d}" for i in range(1, 6)]


def fixtures_and_cases():
    # Physical identity includes start microseconds, not only textual trace/id.
    spans = [
        (PROJECT, "root", TRACES[0], 1_000_000, "", 1, 0),
        (PROJECT, "child", TRACES[0], 1_000_000, "root", 1, 0),
        (PROJECT, "root", TRACES[0], 2_000_000, "different-parent", 1, 0),
        (PROJECT, "changed", TRACES[1], 1_000_000, "", 1, 0),
        (PROJECT, "changed", TRACES[1], 1_000_000, "root", 2, 0),
        (PROJECT, "deleted", TRACES[2], 1_000_000, "", 1, 0),
        (PROJECT, "deleted", TRACES[2], 1_000_000, "", 2, 1),
        (PROJECT, "inline", TRACES[3], 1_000_000, "root", 1, 0),
        (PROJECT, "foreign-only", TRACES[4], 1_000_000, "", 1, 0),
        (OTHER, "root", TRACES[0], 1_000_000, "", 1, 0),
    ]
    scores = [(PROJECT, TRACES[i], "", 0, 0) for i in range(3)] + [
        (PROJECT, "", "inline", 0, 0),
        (OTHER, TRACES[4], "", 0, 0),
        (PROJECT, TRACES[4], "", 1, 0),
        (PROJECT, TRACES[4], "", 0, 1),
    ]
    yes = sorted([("root", 1_000_000), ("inline", 1_000_000)])
    no = sorted(
        [
            ("child", 1_000_000),
            ("root", 2_000_000),
            ("changed", 1_000_000),
            ("foreign-only", 1_000_000),
        ]
    )
    cases = [
        ("is_not_null", None, yes),
        ("is_null", None, no),
        ("equals", "ÉQUIPE", yes),
        ("in", ["équipe", "absent"], yes),
        ("not_equals", "absent", yes),
        ("equals", "absent", []),
    ]
    return spans, scores, cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-read-only", action="store_true", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    initialize_candidate()
    from clickhouse_driver import Client
    from tracer.services.clickhouse.query_builders.filters import (
        ClickHouseFilterBuilder,
    )

    spans, scores, cases = fixtures_and_cases()
    c = Client(
        "127.0.0.1",
        port=args.port,
        database="default",
        user=os.environ.get("OBSERVE_CH_USER", "default"),
        password=os.environ.get("OBSERVE_CH_PASSWORD", ""),
        connect_timeout=3,
        send_receive_timeout=5,
        settings={
            "readonly": 2,
            "max_execution_time": 2,
            "max_threads": 1,
            "max_memory_usage": 64 * 1024**2,
            "max_result_rows": 100,
            "max_result_bytes": 1024**2,
            "use_query_cache": 0,
        },
    )
    results = []
    try:
        identity = c.execute("SELECT hostName(), currentDatabase(), version()")[0]
        if identity[:2] != (args.expected_server, "default"):
            raise replay.ReplayError("DATABASE_TARGET_MISMATCH")
        for op, value, expected in cases:
            compiler = ClickHouseFilterBuilder(
                query_mode=ClickHouseFilterBuilder.QUERY_MODE_SPAN,
                project_id=PROJECT,
                score_date_scope=False,
                resolved_candidate_spans_table="literal_candidates",
            )
            predicate, params = compiler.translate(
                [
                    {
                        "column_id": LABEL,
                        "filter_config": {
                            "col_type": "ANNOTATION",
                            "filter_type": "text",
                            "filter_op": op,
                            "filter_value": value,
                        },
                    }
                ]
            )
            predicate = predicate.replace(
                "model_hub_score AS s FINAL", "literal_scores AS s"
            )
            assert "FROM spans" not in predicate and "model_hub_score" not in predicate
            sql = """WITH literal_candidates AS (
                SELECT toUUID(row.1) AS project_id, row.2 AS id, row.3 AS trace_id,
                    fromUnixTimestamp64Micro(toInt64(row.4)) AS start_time,
                    argMax(row.5, row.6) AS parent_span_id
                FROM (SELECT arrayJoin(%(spans)s) AS row)
                GROUP BY project_id, id, trace_id, start_time
                HAVING argMax(row.7, row.6) = 0
            ), literal_scores AS (
                SELECT toUUID(row.1) AS tracer_project_id, toUUIDOrNull(row.2) AS trace_id,
                    row.3 AS observation_span_id, row.4 AS deleted,
                    row.5 AS _peerdb_is_deleted, toUUID(%(label)s) AS label_id,
                    '{"text":"équipe"}' AS value
                FROM (SELECT arrayJoin(%(scores)s) AS row)
            ) SELECT id, toUnixTimestamp64Micro(start_time)
              FROM literal_candidates WHERE project_id = toUUID(%(project_id)s) AND """
            actual = c.execute(
                sql + predicate + " ORDER BY id, start_time",
                {
                    **params,
                    "project_id": PROJECT,
                    "label": LABEL,
                    "spans": spans,
                    "scores": scores,
                },
            )
            results.append(
                {
                    "operator": op,
                    "matched": actual == expected,
                    "actual_fixture_ids": actual,
                    "expected_fixture_ids": expected,
                }
            )
    finally:
        c.disconnect()
    result = {
        "captured_at": datetime.now(UTC).isoformat(),
        "source_sha256": source_fingerprint(),
        "engine_version": identity[2],
        "source": "literal_CTE_only_no_customer_table_or_fixture_writes",
        "qualified_customer_data": False,
        "passed": sum(x["matched"] for x in results),
        "executed": len(results),
        "results": results,
    }
    replay.private_write(args.output, result)
    print(replay.canonical(result))


if __name__ == "__main__":
    main()
