"""Pure offline independent-oracle contract tests; no SQL or engine execution."""

from copy import deepcopy
import unittest
from uuid import NAMESPACE_URL, UUID, uuid5

import replay_observe_filters as replay
from observe_eval_reference import read_latest_eval_rows, reference_membership, resolve_configs, source_layout


def uid(name):
    return str(uuid5(NAMESPACE_URL, "eval-reference-" + name))


PROJECT, OTHER, CONFIG, TEMPLATE, TRACE = map(uid, ("p", "other", "c", "template", "trace"))
SCOPE = {"organization_id": uid("org"), "workspace_id": uid("workspace"), "project_id": PROJECT}


def document(kind="SCORE"):
    return {
        "scope": SCOPE, "authorized_projects": [PROJECT, OTHER],
        "captured_at": "2026-09-05T00:00:00Z", "transaction_read_only": True,
        "eval_config_inventory_complete": True,
        "eval_config_inventory": [{"config_id": CONFIG, "project_id": PROJECT,
            "template_id": TEMPLATE, "config_output": kind,
            "output_type_normalized": {"SCORE": "percentage", "PASS_FAIL": "pass_fail", "CHOICES": "deterministic"}.get(kind),
            "template_deleted": False}],
    }


def source(table="tracer_eval_logger"):
    direct = table.endswith("_v2")
    return {
        "table": table, "database": "synthetic", "server_version": "25.3.14.14",
        "captured_at": "2026-09-05T00:00:00Z", "engine": "ReplacingMergeTree",
        "sorting_key": "custom_eval_config_id, created_at, id", "partition_key": "toYYYYMM(created_at)",
        "uint64_as_string": False,
        "columns": {
            "id": "UUID", "custom_eval_config_id": "Nullable(UUID)",
            "trace_id": "Nullable(UUID)", "observation_span_id": "Nullable(String)",
            "output_float": "Nullable(Float64)", "output_bool": "Nullable(UInt8)",
            "output_str": "Nullable(String)", "output_str_list": "String", "error": "UInt8",
            **({"_version": "UInt64", "is_deleted": "UInt8"} if direct else {
                "_peerdb_version": "UInt64", "_peerdb_is_deleted": "UInt8", "deleted": "Nullable(UInt8)",
            }),
        },
    }


def row(name="live", **changes):
    return {
        "id": uid(name), "custom_eval_config_id": CONFIG, "trace_id": TRACE,
        "observation_span_id": "span", "created_at": "2025-08-01T00:00:00Z",
        "output_float": 0.5, "output_bool": None, "output_str": None, "output_str_list": "[]",
        "error": 0, "_peerdb_version": 1, "_peerdb_is_deleted": 0, "deleted": 0,
        "_version": 1, "is_deleted": 0, **changes,
    }


class Capture:
    """Fake transport attests a whole synthetic store, not a result sample."""
    def __init__(self, rows, mutate=None):
        self.rows, self.calls, self.mutate = rows, [], mutate

    def __call__(self, stage, proof):
        assert stage in {"ids", "versions"}
        self.calls.append((stage, deepcopy(proof)))
        reply = {"proof_sha256": replay.digest(proof), "exhausted": True,
                 "all_history": True, "sampled": False}
        if stage == "ids":
            reply["ids"] = sorted({r["id"] for r in self.rows if r["custom_eval_config_id"] in proof["configs"]})
        else:
            reply.update(completed_ids=proof["ids"], rows=[r for r in self.rows if r["id"] in proof["ids"]])
        if self.mutate:
            self.mutate(stage, reply)
        return reply


class EvalReferenceTests(unittest.TestCase):
    def evaluate(self, rows, op="equals", value=50, kind="SCORE", grain="trace", **kwargs):
        doc = kwargs.pop("document", document(kind))
        src = kwargs.pop("source", source())
        transport = kwargs.pop("read", Capture(rows))
        return reference_membership(doc, SCOPE, {
            "column_id": CONFIG, "filter_config": {"col_type": "EVAL_METRIC", "filter_op": op, "filter_value": value},
        }, [PROJECT, OTHER], src, transport, grain=grain, **kwargs)

    def universe(self, kind="SCORE", grain="trace"):
        return {"complete": True, "independent": True, "grain": grain,
            "metadata_sha256": replay.digest(document(kind)), "scope_sha256": replay.digest(SCOPE),
            "entities": [(PROJECT, TRACE)] if grain == "trace" else [(PROJECT, TRACE, "span")]}

    def test_config_and_template_resolution_keep_each_project(self):
        doc = document()
        doc["eval_config_inventory"].append({**doc["eval_config_inventory"][0], "config_id": uid("other-config"), "project_id": OTHER})
        self.assertEqual(set(resolve_configs(doc, SCOPE, TEMPLATE, [PROJECT, OTHER])), {CONFIG, uid("other-config")})
        self.assertEqual(resolve_configs(doc, SCOPE, CONFIG, [PROJECT, OTHER]), {CONFIG: {"project_id": PROJECT, "output_type": "SCORE"}})
        self.assertEqual(resolve_configs(doc, SCOPE, uid("absent"), [PROJECT, OTHER]), {})

    def test_metadata_rejects_samples_foreign_conflicting_or_deleted(self):
        mutations = [
            lambda d: d.pop("eval_config_inventory_complete"),
            lambda d: d.update(transaction_read_only=False),
            lambda d: d.update(authorized_projects=[PROJECT]),
            lambda d: d["eval_config_inventory"][0].update(project_id=uid("foreign")),
            lambda d: d["eval_config_inventory"].append(d["eval_config_inventory"][0]),
            lambda d: d["eval_config_inventory"][0].update(template_deleted=True),
            lambda d: d["eval_config_inventory"][0].update(output_type_normalized="deterministic"),
            lambda d: d["eval_config_inventory"][0].update(config_output="unknown", output_type_normalized=None),
        ]
        for mutate in mutations:
            doc = document()
            mutate(doc)
            with self.subTest(document=doc), self.assertRaises(replay.ReplayError):
                self.evaluate([row()], document=doc)

    def test_whole_id_and_version_exhaustion_is_mandatory(self):
        for stage in ("ids", "versions"):
            for key, value in (("exhausted", False), ("all_history", False), ("sampled", True), ("proof_sha256", "wrong")):
                def mutate(actual_stage, reply):
                    if actual_stage == stage:
                        reply[key] = value
                with self.subTest(stage=stage, key=key), self.assertRaises(replay.ReplayError):
                    self.evaluate([], read=Capture([row()], mutate))
        for change in ({"completed_ids": []}, {"rows": []}, {"rows": [row("unrequested")]}):
            with self.subTest(change=change), self.assertRaises(replay.ReplayError):
                self.evaluate([], read=Capture([row()], lambda stage, reply: reply.update(change) if stage == "versions" else None))

    def test_empty_exhaustive_store_is_not_an_incomplete_capture(self):
        transport = Capture([])
        actual, evidence = self.evaluate([], read=transport)
        self.assertEqual(actual, set())
        self.assertEqual(evidence["id_count"], 0)
        self.assertEqual([stage for stage, _ in transport.calls], ["ids", "versions"])
        self.assertEqual(self.evaluate([], "is_null", universe=self.universe())[0], {(PROJECT, TRACE)})

    def test_latest_state_is_whole_row_across_physical_coordinates(self):
        for table in ("tracer_eval_logger", "tracer_eval_logger_v2"):
            src = source(table)
            version = "_version" if table.endswith("_v2") else "_peerdb_version"
            for change in ({"output_float": 0.8}, {"output_float": None}, {"error": 1},
                           {"is_deleted": 1} if table.endswith("_v2") else {"_peerdb_is_deleted": 1},
                           {"is_deleted": 1} if table.endswith("_v2") else {"deleted": 1}):
                rows = [row(), row(**{version: 2, "created_at": "2026-09-05T00:00:00Z", **change})]
                with self.subTest(table=table, change=change):
                    self.assertEqual(self.evaluate(rows, source=src)[0], set())
                    self.assertEqual(self.evaluate(rows, "is_null", source=src, universe=self.universe())[0],
                                     set() if change == {"output_float": 0.8} else {(PROJECT, TRACE)})

    def test_latest_config_and_trace_movement_cannot_revive_old_identity(self):
        self.assertEqual(self.evaluate([row(), row(_peerdb_version=2, custom_eval_config_id=uid("foreign-config"))])[0], set())
        self.assertEqual(self.evaluate([row(), row(_peerdb_version=2, trace_id=uid("new-trace"))])[0], {(PROJECT, uid("new-trace"))})

    def test_latest_clear_error_and_tombstone_apply_to_each_output_type(self):
        for kind, good, clear, value in (
            ("SCORE", {"output_float": 0}, {"output_float": None}, 0),
            ("PASS_FAIL", {"output_bool": 0}, {"output_bool": None}, "Failed"),
            ("CHOICES", {"output_str": "yes", "output_str_list": '["yes"]'},
             {"output_str": None, "output_str_list": "[]"}, "yes"),
        ):
            self.assertEqual(self.evaluate([row(**good)], value=value, kind=kind)[0], {(PROJECT, TRACE)})
            for table in ("tracer_eval_logger", "tracer_eval_logger_v2"):
                src = source(table)
                version, dead = ("_version", "is_deleted") if table.endswith("_v2") else ("_peerdb_version", "_peerdb_is_deleted")
                for changes in (clear, {"error": 1}, {dead: 1}):
                    rows = [row(**good), row(**{**good, version: 2, **changes})]
                    with self.subTest(kind=kind, table=table, changes=changes):
                        self.assertEqual(self.evaluate(rows, value=value, kind=kind, source=src)[0], set())
                        self.assertEqual(self.evaluate(rows, "is_null", kind=kind, source=src, universe=self.universe(kind))[0], {(PROJECT, TRACE)})
        self.assertEqual(self.evaluate([row(output_str_list='[""]')], "is_not_null", kind="CHOICES")[0], {(PROJECT, TRACE)})

    def test_whole_id_replies_must_prove_scoped_origins(self):
        foreign = row(custom_eval_config_id=uid("foreign-config"))
        def mutate(stage, reply):
            if stage == "ids":
                reply["ids"] = [foreign["id"]]
        with self.assertRaisesRegex(replay.ReplayError, "ID_DISCOVERY_SCOPE_UNPROVEN"):
            self.evaluate([], read=Capture([foreign], mutate))

    def test_null_soft_delete_is_not_null_cdc_liveness(self):
        self.assertEqual(self.evaluate([row(deleted=None)])[0], {(PROJECT, TRACE)})
        src = source()
        src["columns"]["_peerdb_is_deleted"] = "Nullable(UInt8)"
        with self.assertRaisesRegex(replay.ReplayError, "FLAG_TYPE"):
            self.evaluate([row(_peerdb_is_deleted=None)], source=src)

    def test_version_conflicts_and_duplicates(self):
        with self.assertRaisesRegex(replay.ReplayError, "LATEST_VERSION_CONFLICT"):
            self.evaluate([row(), row(output_float=0.8)])
        self.assertEqual(self.evaluate([row(), row()])[0], {(PROJECT, TRACE)})
        self.assertEqual(self.evaluate([row(), row(output_float=0.8), row(_peerdb_version=2)])[0], {(PROJECT, TRACE)})
        self.assertEqual(self.evaluate([row(_peerdb_version=2**64-1), row(_peerdb_version=2**64-2, output_float=0.8)])[0], {(PROJECT, TRACE)})
        for revision in (True, -1, 2**64, 1.0, "1"):
            with self.subTest(revision=revision), self.assertRaises(replay.ReplayError):
                self.evaluate([row(_peerdb_version=revision)])
        self.assertEqual(self.evaluate([row(_peerdb_version=str(2**64-1))], source={**source(), "uint64_as_string": True})[0], {(PROJECT, TRACE)})

    def test_score_public_units_and_operators(self):
        for op, value, expected in (
            ("equals", 50, True), ("equals", 0.5, False), ("not_equals", 50, False),
            ("in", [40, 50], True), ("not_in", [50, 60], False),
            ("between", [50, 60], True), ("not_between", [50, 60], False),
            ("greater_than", 50, False), ("greater_than_or_equal", 50, True),
            ("less_than", 50, False), ("less_than_or_equal", 50, True),
        ):
            with self.subTest(op=op, value=value):
                self.assertEqual(bool(self.evaluate([row()], op, value)[0]), expected)
        self.assertEqual(self.evaluate([row(output_float=0.29)], "equals", 29)[0], {(PROJECT, TRACE)})
        for value in (True, "50", float("inf"), float("nan"), 2**10000):
            with self.subTest(type=type(value)), self.assertRaises(replay.ReplayError):
                self.evaluate([row()], value=value)

    def test_declared_version_signedness_boundaries_and_raw_order(self):
        for table, declared, lo, hi in (
            ("tracer_eval_logger", "Int64", -(2**63), 2**63 - 1),
            ("tracer_eval_logger", "UInt64", 0, 2**64 - 1),
            ("tracer_eval_logger_v2", "UInt64", 0, 2**64 - 1),
        ):
            src = source(table)
            version = "_version" if table.endswith("_v2") else "_peerdb_version"
            src["columns"][version] = declared
            for quoted in (False, True):
                src["uint64_as_string"] = quoted
                def raw(value):
                    return str(value) if quoted else value
                for older, newer in ((lo, lo + 1), (hi - 1, hi), *(((-1, 0),) if lo < 0 else ())):
                    rows = [row(**{version: raw(newer)}), row(output_float=.8, **{version: raw(older)})]
                    with self.subTest(table=table, declared=declared, quoted=quoted, versions=(older, newer)):
                        self.assertEqual(self.evaluate(rows, source=src)[0], {(PROJECT, TRACE)})
                        latest, _ = read_latest_eval_rows(resolve_configs(document(), SCOPE, CONFIG, [PROJECT, OTHER]),
                            src, Capture(rows), replay.digest(document()))
                        self.assertEqual(latest, [rows[0]])
                        self.assertIs(type(latest[0][version]), str if quoted else int)
                invalid = (raw(lo - 1), raw(hi + 1), True, False, None, 1.0)
                invalid += ("", "-", "--1", "+1", " 1", "1.0", "１", 1) if quoted else ("1", "-1")
                for value in invalid:
                    with self.subTest(declared=declared, quoted=quoted, invalid=value), self.assertRaises(replay.ReplayError):
                        self.evaluate([row(**{version: value})], source=src)

    def test_signed_version_conflicts_and_store_type_gates(self):
        src = source()
        src["columns"]["_peerdb_version"] = "Int64"
        with self.assertRaisesRegex(replay.ReplayError, "LATEST_VERSION_CONFLICT"):
            self.evaluate([row(_peerdb_version=-1), row(_peerdb_version=-1, output_float=.8)], source=src)
        for table, version, unsupported in (
            ("tracer_eval_logger_v2", "_version", ("Int64", "Nullable(UInt64)", "String")),
            ("tracer_eval_logger", "_peerdb_version", ("Int32", "Nullable(Int64)", "Float64")),
        ):
            for declared in unsupported:
                src = source(table)
                src["columns"][version] = declared
                with self.subTest(table=table, declared=declared), self.assertRaisesRegex(replay.ReplayError, "RAW_TYPES_UNSUPPORTED"):
                    source_layout(src)

    def test_value_negatives_are_existential_not_entity_complements(self):
        rows = [row("one"), row("two", output_float=0.8)]
        for op in ("equals", "not_equals", "in", "not_in"):
            self.assertEqual(self.evaluate(rows, op, [50] if op.endswith("in") else 50)[0], {(PROJECT, TRACE)})

    def test_pass_fail_uses_only_typed_bool_and_rejects_partial_tokens(self):
        for op, value, expected in (("equals", "Passed", True), ("not_in", ["Failed"], True),
                                    ("in", ["Passed", "Failed"], True), ("equals", False, False)):
            self.assertEqual(bool(self.evaluate([row(output_bool=1, output_float=0)], op, value, "PASS_FAIL")[0]), expected)
        for value in (["Passed", "invalid"], ["Passed", None], ["Passed", 2], []):
            with self.subTest(value=value), self.assertRaises(replay.ReplayError):
                self.evaluate([row(output_bool=1)], "not_in", value, "PASS_FAIL")
        for raw in ("1", True, 2):
            with self.subTest(raw=raw), self.assertRaises(replay.ReplayError):
                self.evaluate([row(output_bool=raw)], "equals", "Passed", "PASS_FAIL")
        src = source()
        src["columns"]["output_bool"] = "Nullable(Bool)"
        self.assertEqual(self.evaluate([row(output_bool=True)], "equals", "Passed", "PASS_FAIL", source=src)[0], {(PROJECT, TRACE)})

    def test_choices_union_literal_negatives_and_case_contract(self):
        rows = [row(output_str="scalar", output_str_list='["50%_done", "a\\\\b"]')]
        for op, value, expected in (("in", ["scalar"], True), ("equals", "50%_done", True),
            ("equals", "SCALAR", False), ("not_in", ["scalar", "other"], False),
            ("contains", "50%_", True), ("contains", "50XX", False),
            ("starts_with", "50%_", True), ("ends_with", "DONE", True),
            ("contains", r"a\b", True), ("not_contains", ["missing", "scalar"], False)):
            with self.subTest(op=op, value=value):
                self.assertEqual(bool(self.evaluate(rows, op, value, "CHOICES")[0]), expected)
        self.assertEqual(self.evaluate([row(output_str=None, output_str_list='["other"]')], "not_contains", "x", "CHOICES")[0], {(PROJECT, TRACE)})
        for raw in ("bad", "{}", '[1]', None):
            with self.subTest(raw=raw), self.assertRaises(replay.ReplayError):
                self.evaluate([row(output_str_list=raw)], "is_not_null", None, "CHOICES")

    def test_unicode_requires_explicit_engine_fold_not_python_lower(self):
        rows = [row(output_str="ΟΣ")]
        with self.assertRaisesRegex(replay.ReplayError, "ENGINE_UNICODE_FOLD_REQUIRED"):
            self.evaluate(rows, "contains", "ΟΣ", "CHOICES")
        # Constant engine-compatible transform fixture; not an engine test.
        self.assertEqual(self.evaluate(rows, "contains", "ΟΣ", "CHOICES", fold={"ΟΣ": "οσ"}.__getitem__)[0], {(PROJECT, TRACE)})

    def test_targets_keep_project_trace_span_and_no_score_root_fallback(self):
        doc = document()
        doc["eval_config_inventory"].append({**doc["eval_config_inventory"][0], "config_id": uid("other-config"), "project_id": OTHER})
        rows = [row(), row("foreign", custom_eval_config_id=uid("other-config")), row("trace-only", observation_span_id=None)]
        self.assertEqual(self.evaluate(rows, grain="span", document=doc)[0], {(PROJECT, TRACE, "span")})
        targets, _ = reference_membership(doc, SCOPE, {"column_id": TEMPLATE, "filter_config": {
            "col_type": "EVAL_METRIC", "filter_op": "equals", "filter_value": 50,
        }}, [PROJECT, OTHER], source(), Capture(rows), grain="span")
        self.assertEqual(targets, {(PROJECT, TRACE, "span"), (OTHER, TRACE, "span")})
        self.assertEqual(self.evaluate([row(observation_span_id=None)])[0], {(PROJECT, TRACE)})
        self.assertEqual(self.evaluate([row(observation_span_id=None)], grain="span")[0], set())
        for trace in (None, "", str(UUID(int=0))):
            self.assertEqual(self.evaluate([row(trace_id=trace)])[0], set())

    def test_missing_requires_certified_independent_matching_universe(self):
        for u in (None, {**self.universe(), "complete": False}, {**self.universe(), "independent": False},
                  {**self.universe(), "metadata_sha256": "wrong"}, {**self.universe(), "grain": "span"},
                  {**self.universe(), "entities": [(uid("foreign"), TRACE)]}):
            with self.subTest(universe=u), self.assertRaises(replay.ReplayError):
                self.evaluate([], "is_null", universe=u)
        self.assertEqual(self.evaluate([row(output_float=None)], "is_null", grain="span", universe=self.universe(grain="span"))[0], {(PROJECT, TRACE, "span")})

    def test_source_type_and_raw_row_proof_fail_closed(self):
        for change in ({"table": "other"}, {"engine": "MergeTree"}, {"columns": {}}, {"sorting_key": ""}):
            with self.subTest(change=change), self.assertRaises(replay.ReplayError):
                self.evaluate([row()], source={**source(), **change})
        incomplete = row()
        del incomplete["output_str_list"]
        with self.assertRaises(replay.ReplayError):
            self.evaluate([incomplete])
        for raw in ("0.5", True, float("nan")):
            with self.subTest(raw=raw), self.assertRaises(replay.ReplayError):
                self.evaluate([row(output_float=raw)])


if __name__ == "__main__":
    unittest.main()
