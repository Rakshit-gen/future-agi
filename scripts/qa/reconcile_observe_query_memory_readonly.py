#!/usr/bin/env python3
"""Reconcile recorded candidate query IDs with memory/timing, without SQL text.

This only SELECTs system.query_log. It never flushes logs or changes settings,
roles or production memory configuration. Log visibility can lag completion;
missing IDs stay explicitly unverified. Reference queries are excluded.
"""

import argparse
from datetime import datetime, timedelta, timezone
import math
import os
from pathlib import Path
import re

import replay_observe_filters as replay


def recorded_queries(rows):
    ids, starts, fingerprints = set(), [], set()
    for row in rows:
        queries = row.get("queries", [])
        if not queries:
            continue
        fingerprint = row.get("source_sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise replay.ReplayError("SOURCE_FINGERPRINT_REQUIRED")
        fingerprints.add(fingerprint)
        starts.append(
            datetime.fromisoformat(row["started_at_utc"]).astimezone(timezone.utc)
        )
        for query in queries:
            query_id = query["query_id"]
            if not re.fullmatch(r"observe-local-replay-[0-9a-f]{12}-[0-9]+", query_id):
                raise replay.ReplayError("INVALID_RECORDED_QUERY_ID")
            ids.add(query_id)
    if not ids or len(ids) > 2000 or len(fingerprints) != 1:
        raise replay.ReplayError("EMPTY_OVERSIZED_OR_MIXED_SOURCE_LEDGER")
    return sorted(ids), min(starts), next(iter(fingerprints))


def summarize(ids, records):
    finishes, errors = {}, {}
    for query_id, event, duration_ms, memory, read_rows, read_bytes, code in records:
        if query_id not in ids:
            raise replay.ReplayError("UNREQUESTED_QUERY_LOG_ROW")
        entry = {
            "query_id": query_id,
            "event": event,
            "duration_ms": duration_ms,
            "memory_bytes": memory,
            "read_rows": read_rows,
            "read_bytes": read_bytes,
            "exception_code": code,
        }
        target = finishes if event == "QueryFinish" and code == 0 else errors
        if query_id in target and entry != target[query_id]:
            raise replay.ReplayError("CONFLICTING_QUERY_LOG_ROWS")
        target[query_id] = entry
    if finishes.keys() & errors.keys():
        raise replay.ReplayError("CONFLICTING_QUERY_LOG_TERMINAL_EVENTS")
    # Failed/aborted queries are essential when sizing memory, not exclusions
    # from a successful-query-only percentile.
    peaks = sorted(
        row["memory_bytes"] for row in (*finishes.values(), *errors.values())
    )
    missing = sorted(set(ids) - finishes.keys() - errors.keys())
    return {
        "requested": len(ids),
        "query_finish": len(finishes),
        "query_errors": len(errors),
        "missing_query_ids": missing,
        "fully_reconciled": not missing and not errors and len(finishes) == len(ids),
        "max_query_memory_bytes": max(peaks, default=None),
        "p95_query_memory_bytes": peaks[math.ceil(len(peaks) * 0.95) - 1]
        if peaks
        else None,
        "percentile_method": "nearest_rank",
        "memory_includes_failed_queries": True,
        "memory_is_reported_query_peak_not_process_peak": True,
        # Planning/subquery failures can reach query_log as ExceptionBeforeStart
        # with memory_usage=0. That is not evidence that the failed work used no
        # memory, nor proof of an end-to-end process peak.
        "failed_queries_with_zero_reported_memory": sorted(
            query_id for query_id, row in errors.items() if row["memory_bytes"] == 0
        ),
        "records": [*finishes.values(), *errors.values()],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-read-only", required=True, action="store_true")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--expected-server", required=True)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--ledger", help="JSONL candidate case ledger")
    inputs.add_argument("--report", help="Single JSON candidate probe report")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if Path(args.output).exists():
        raise replay.ReplayError("OUTPUT_EXISTS")
    import json
    from clickhouse_driver import Client

    if args.report:
        ids, start, fingerprint = recorded_queries([replay.read_json(args.report)])
    else:
        with Path(args.ledger).open() as source:
            ids, start, fingerprint = recorded_queries(
                json.loads(line) for line in source if line.strip()
            )
    now = datetime.now(timezone.utc)
    if start > now or now - start > timedelta(hours=2):
        raise replay.ReplayError("ONLY_RECENT_LEDGER_RECONCILIATION_ALLOWED")
    client = Client(
        "127.0.0.1",
        port=args.port,
        database="default",
        user=os.environ.get("OBSERVE_CH_USER", "default"),
        password=os.environ.get("OBSERVE_CH_PASSWORD", ""),
        connect_timeout=3,
        send_receive_timeout=6,
        settings={
            "readonly": 2,
            "max_execution_time": 3,
            "max_threads": 1,
            "max_memory_usage": 128 * 1024**2,
            "max_bytes_to_read": 128 * 1024**2,
            "max_result_rows": 2001,
            "max_result_bytes": 2 * 1024**2,
            "read_overflow_mode": "throw",
            "result_overflow_mode": "throw",
            "timeout_overflow_mode": "throw",
            "use_query_cache": 0,
        },
    )
    try:
        if client.execute("SELECT hostName()")[0][0] != args.expected_server:
            raise replay.ReplayError("DATABASE_TARGET_MISMATCH")
        records = client.execute(
            """SELECT query_id, toString(type), query_duration_ms, memory_usage,
                      read_rows, read_bytes, exception_code
               FROM system.query_log
               WHERE event_date >= toDate(%(start)s)
                 AND event_time >= %(start)s AND event_time <= %(end)s
                 AND query_id IN %(ids)s AND type != 'QueryStart'
               LIMIT 2001""",
            {"start": start - timedelta(seconds=1), "end": now, "ids": ids},
        )
        if len(records) > 2000:
            raise replay.ReplayError("QUERY_LOG_SENTINEL_REACHED")
        report = {
            "captured_at": now.isoformat(),
            "server": args.expected_server,
            "candidate_source_sha256": fingerprint,
            "candidate_queries_only": True,
            "production_configuration_changed": False,
            **summarize(ids, records),
        }
        replay.private_write(args.output, report)
        print(
            replay.canonical(
                {key: value for key, value in report.items() if key != "records"}
            )
        )
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
