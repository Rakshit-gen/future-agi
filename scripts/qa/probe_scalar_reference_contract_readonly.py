#!/usr/bin/env python3
"""Run constant-only scalar oracle truth tables on an explicitly verified host.

This opens no customer tables and changes no server state. It is supplementary
engine evidence, not production-data query qualification or an SLO benchmark.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from clickhouse_driver import Client

import test_scalar_reference_engine as fixture


def fingerprint():
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for name in sorted(
        (
            Path(__file__).name,
            "test_scalar_reference_engine.py",
            "observe_trace_id_reference.py",
        )
    ):
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-read-only", action="store_true", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be a new evidence file")
    before = fingerprint()
    settings = {
        "readonly": 2,
        "max_execution_time": 2,
        "max_threads": 1,
        "max_memory_usage": 32 * 1024**2,
        "max_rows_to_read": 10000,
        "max_bytes_to_read": 32 * 1024**2,
        "max_result_rows": 100,
        "max_result_bytes": 1024**2,
        "timeout_overflow_mode": "throw",
        "read_overflow_mode": "throw",
        "result_overflow_mode": "throw",
        "use_query_cache": 0,
    }
    client = Client(
        "127.0.0.1",
        port=args.port,
        database="default",
        user=os.getenv("OBSERVE_CH_USER", "default"),
        password=os.getenv("OBSERVE_CH_PASSWORD", ""),
        settings=settings,
        connect_timeout=5,
        send_receive_timeout=10,
    )
    calls = []

    def query(sql, _format):
        normalized = " ".join(sql.split())
        if not (
            normalized == "SELECT lowerUTF8('ABC')"
            or normalized.startswith("SELECT trace_id FROM ( SELECT t.1 AS trace_id,")
        ):
            raise RuntimeError("unexpected non-fixture SQL")
        rows, columns = client.execute(sql, with_column_types=True)
        calls.append(hashlib.sha256(sql.encode()).hexdigest())
        return json.dumps(
            {"data": [dict(zip((c[0] for c in columns), row)) for row in rows]}
        )

    try:
        host, version = client.execute("SELECT hostName(), version()")[0]
        if host != args.expected_server:
            raise RuntimeError("server identity mismatch")
        engine = SimpleNamespace(query=query)
        test_type = fixture.ScalarReferenceEngineTests
        # Default unittest discovery skips without chdb. This explicitly
        # authorized runner supplies the verified read-only engine instead.
        with (
            patch.object(fixture, "chdb", engine),
            patch.object(test_type, "__unittest_skip__", False),
        ):
            result = unittest.TextTestRunner(verbosity=1).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(test_type)
            )
        unchanged = before == fingerprint()
        passed = result.wasSuccessful() and not result.skipped and unchanged
        report = {
            "passed": passed,
            "server": host,
            "version": version,
            "source_fingerprint": before,
            "source_unchanged": unchanged,
            "tests": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "constant_query_count": len(calls),
            "query_hashes": calls,
            "settings": settings,
            "customer_data_read": False,
            "qualification": "OPERATOR_ENGINE_ONLY_NOT_PRODUCTION_BENCHMARK",
        }
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k != "query_hashes"}))
        return 0 if passed else 1
    finally:
        client.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
