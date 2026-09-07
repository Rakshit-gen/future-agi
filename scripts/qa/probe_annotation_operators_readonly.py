#!/usr/bin/env python3
"""Execute candidate annotation predicates over literal rows, never DB tables.

Supplementary engine regression probe, NOT customer-data or API qualification.
Uses the actual local annotation value compiler; only its relation source and
entity-column hooks are replaced by a constant CTE. No fixtures are inserted.
"""

import argparse
import json
import os
from datetime import UTC, datetime

import replay_observe_filters as replay
from replay_observe_queries_readonly import initialize_candidate, source_fingerprint


LABEL = "22222222-2222-4222-8222-222222222222"


def fixtures_and_cases():
    payloads = {
        "missing": {},
        "null": {"rating": None},
        "string": {"rating": "0"},
        "boolean": {"rating": False},
        "object": {"rating": {}},
        "array": {"rating": []},
        "invalid_rating_fallback": {"rating": None, "value": 0},
        "zero_rating": {"rating": 0},
        "zero_value": {"value": 0},
        "negative": {"rating": -1},
        "fraction": {"rating": 1.5},
        "rating_precedence": {"rating": 4, "value": 0},
        "accent_upper": {"text": "ÉQUIPE"},
        "accent_lower": {"text": "équipe"},
        "other": {"text": "OTHER"},
        "literal": {"text": "other_%"},
        "blank": {"text": ""},
    }
    numbers = {
        "zero_rating": 0,
        "zero_value": 0,
        "negative": -1,
        "fraction": 1.5,
        "rating_precedence": 4,
    }
    cases = []
    for op, value, expected in (
        ("equals", 0, lambda v: v == 0),
        ("not_equals", 0, lambda v: v != 0),
        ("greater_than", 0, lambda v: v > 0),
        ("greater_than_or_equal", 0, lambda v: v >= 0),
        ("less_than", 0, lambda v: v < 0),
        ("less_than_or_equal", 0, lambda v: v <= 0),
        ("between", [-1, 1.5], lambda v: -1 <= v <= 1.5),
        ("not_between", [-1, 1.5], lambda v: not -1 <= v <= 1.5),
        ("in", [0, 1.5], lambda v: v in [0, 1.5]),
        ("not_in", [0, 1.5], lambda v: v not in [0, 1.5]),
    ):
        cases.append(
            ("number", op, value, sorted(k for k, v in numbers.items() if expected(v)))
        )
    for op, value, expected in (
        ("equals", "équipe", ["accent_lower", "accent_upper"]),
        ("not_equals", "équipe", ["literal", "other"]),
        ("in", ["équipe", "OTHER_%"], ["accent_lower", "accent_upper", "literal"]),
        ("not_in", ["équipe", "OTHER_%"], ["other"]),
        ("contains", "_%", ["literal"]),
        ("not_contains", "_%", ["accent_lower", "accent_upper", "other"]),
        ("starts_with", "ÉQ", ["accent_lower", "accent_upper"]),
        ("ends_with", "_%", ["literal"]),
    ):
        cases.append(("text", op, value, expected))
    return [
        (key, json.dumps(value, ensure_ascii=False)) for key, value in payloads.items()
    ], cases


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

    class LiteralScorePredicate(ClickHouseFilterBuilder):
        def _score_entity_select(self, extra_where="", **kwargs):
            return "SELECT s.id FROM literal_scores AS s WHERE 1 " + extra_where

        def _score_entity_column(self):
            return "id"

    fixtures, cases = fixtures_and_cases()
    client = Client(
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
            "max_memory_usage": 32 * 1024**2,
            "max_result_rows": 100,
            "max_result_bytes": 1024**2,
            "result_overflow_mode": "throw",
            "timeout_overflow_mode": "throw",
            "use_query_cache": 0,
        },
    )
    results = []
    try:
        identity = client.execute("SELECT hostName(), currentDatabase(), version()")[0]
        if identity[:2] != (args.expected_server, "default"):
            raise replay.ReplayError("DATABASE_TARGET_MISMATCH")
        for kind, op, value, expected in cases:
            predicate, params = LiteralScorePredicate().translate(
                [
                    {
                        "column_id": LABEL,
                        "filter_config": {
                            "col_type": "ANNOTATION",
                            "filter_type": kind,
                            "filter_op": op,
                            "filter_value": value,
                        },
                    }
                ]
            )
            sql = (
                """WITH literal_scores AS (
                SELECT entry.1 AS id, entry.2 AS value,
                    toUUID(%(fixture_label)s) AS label_id
                FROM (SELECT arrayJoin(%(fixtures)s) AS entry)
            ) SELECT id FROM literal_scores WHERE """
                + predicate
                + " ORDER BY id"
            )
            actual = [
                r[0]
                for r in client.execute(
                    sql,
                    {
                        **params,
                        "fixture_label": LABEL,
                        "fixtures": fixtures,
                    },
                )
            ]
            results.append(
                {
                    "type": kind,
                    "operator": op,
                    "matched": actual == expected,
                    "actual_fixture_ids": actual,
                    "expected_fixture_ids": expected,
                }
            )
    finally:
        client.disconnect()
    result = {
        "captured_at": datetime.now(UTC).isoformat(),
        "source_sha256": source_fingerprint(),
        "engine_version": identity[2],
        "source": "literal_CTE_only_no_customer_table_or_fixture_writes",
        "qualified_customer_data": False,
        "passed": sum(r["matched"] for r in results),
        "executed": len(results),
        "cases": results,
    }
    replay.private_write(args.output, result)
    print(replay.canonical(result))
    return 0 if all(r["matched"] for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
