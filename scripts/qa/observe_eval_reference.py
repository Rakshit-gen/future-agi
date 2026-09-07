"""Independent eval target sets; no SQL, application compiler or candidate IDs.

``read(stage, proof)`` is caller-owned and must enforce config/project authority
through its normal scoped reader, never bypass validate_select. For ``ids`` it
exhausts all-history ID discovery under proof['configs']; for ``versions`` it
exhausts ALL versions of proof['ids'], without config/value/identity/date/live
filters. Both replies echo proof_sha256 and attest exhausted/all_history and
sampled=False. Versions also attest completed_ids. Examples are not captures.

Targets are (project, trace) or (project, trace, span), NOT physical pages.
The caller owns independent latest-root/window/six-key span resolution and
cross-read consistency. Membership alone establishes no latency qualification.
"""

import json
import math
import operator
from uuid import UUID

import replay_observe_filters as replay
from observe_relational_metadata import metadata_scope


def require(valid, code):
    if not valid:
        raise replay.ReplayError("REFERENCE_EVAL_" + code)


def identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise replay.ReplayError("REFERENCE_EVAL_INVALID_ID") from None


def resolve_configs(document, scope, eval_id, projects):
    """Resolve captured config/template ownership independently of app metadata."""
    projects = {identifier(p) for p in projects}
    require(
        projects and document.get("eval_config_inventory_complete") is True
        and document.get("transaction_read_only") is True
        and document.get("captured_at")
        and identifier(scope["project_id"]) in projects
        and metadata_scope(document.get("scope")) == metadata_scope(scope)
        and {identifier(p) for p in document.get("authorized_projects", [])} == projects,
        "COMPLETE_SCOPED_METADATA_REQUIRED",
    )
    inventory = document.get("eval_config_inventory")
    require(isinstance(inventory, list), "CONFIG_INVENTORY_REQUIRED")
    rows = {}
    for row in inventory:
        config, project = identifier(row["config_id"]), identifier(row["project_id"])
        require(project in projects and config not in rows, "CONFIG_OWNERSHIP_CONFLICT")
        rows[config] = row
    requested = identifier(eval_id)
    selected = [rows[requested]] if requested in rows else [
        row for row in rows.values() if identifier(row["template_id"]) == requested
    ]
    result = {}
    for row in selected:
        require(row.get("template_deleted") is False, "TEMPLATE_STATE_UNVERIFIED")
        kinds = {
            str(row.get(key) or "").upper().replace("/", "_").replace(" ", "_")
            for key in ("config_output", "output_type_normalized") if row.get(key)
        }
        kinds = { {"CHOICES": "CHOICE", "PERCENTAGE": "SCORE", "DETERMINISTIC": "CHOICE"}.get(kind, kind) for kind in kinds}
        require(len(kinds) == 1 and kinds <= {"SCORE", "PASS_FAIL", "CHOICE"}, "OUTPUT_TYPE_AMBIGUOUS")
        result[identifier(row["config_id"])] = {
            "project_id": identifier(row["project_id"]), "output_type": kinds.pop(),
        }
    require(len({v["output_type"] for v in result.values()}) <= 1, "OUTPUT_TYPE_AMBIGUOUS")
    return result


def source_layout(source):
    """Accept a verified physical layout, not a guessed runtime table default."""
    table = source.get("table")
    require(table in {"tracer_eval_logger", "tracer_eval_logger_v2"}, "SOURCE_UNSUPPORTED")
    require(all(source.get(k) for k in ("database", "server_version", "captured_at", "sorting_key"))
            and "ReplacingMergeTree" in source.get("engine", "")
            and "partition_key" in source and type(source.get("uint64_as_string")) is bool,
            "PHYSICAL_SOURCE_PROOF_REQUIRED")
    direct = table.endswith("_v2")
    version = "_version" if direct else "_peerdb_version"
    live = ("is_deleted",) if direct else ("_peerdb_is_deleted", "deleted")
    columns = source.get("columns", {})
    required = {
        "id": {"UUID"}, "custom_eval_config_id": {"UUID", "Nullable(UUID)"},
        "trace_id": {"Nullable(UUID)", "Nullable(String)"},
        "observation_span_id": {"Nullable(String)"},
        "output_float": {"Nullable(Float64)"}, "output_str": {"Nullable(String)"},
        "output_str_list": {"String"}, "output_bool": {"Nullable(UInt8)", "Nullable(Bool)"},
        "error": {"UInt8", "Bool"}, version: {"UInt64"} if direct else {"Int64", "UInt64"},
        **{key: {"UInt8", "Bool", "Nullable(UInt8)", "Nullable(Bool)"} for key in live},
    }
    require(all(columns.get(key) in types for key, types in required.items()), "RAW_TYPES_UNSUPPORTED")
    return version, live, columns


def read_latest_eval_rows(configs, source, read, metadata_sha256):
    """Require both exhaustion certificates; reduce logical IDs after reading."""
    version, _, columns = source_layout(source)
    signed = columns[version] == "Int64"
    minimum, maximum = (-(2**63), 2**63) if signed else (0, 2**64)
    proof = {"configs": configs, "source": source, "metadata_sha256": metadata_sha256,
             "domain": "scoped_config_ids_then_unfiltered_whole_id_history"}

    def capture(stage, **extra):
        request = {**proof, "stage": stage, **extra}
        reply = read(stage, request)
        require(isinstance(reply, dict), "CAPTURE_REQUIRED")
        require(reply.get("proof_sha256") == replay.digest(request)
                and reply.get("exhausted") is True and reply.get("all_history") is True
                and reply.get("sampled") is False, "WHOLE_SOURCE_EXHAUSTION_REQUIRED")
        return reply

    discovered = capture("ids").get("ids")
    require(isinstance(discovered, list), "ID_INVENTORY_REQUIRED")
    ids = [identifier(value) for value in discovered]
    id_set = set(ids)
    require(len(ids) == len(id_set), "DUPLICATE_DISCOVERY_ID")
    response = capture("versions", ids=sorted(ids))
    require(isinstance(response.get("completed_ids"), list)
            and {identifier(value) for value in response["completed_ids"]} == id_set,
            "WHOLE_VERSION_EXHAUSTION_REQUIRED")
    rows = response.get("rows")
    require(isinstance(rows, list), "VERSION_ROWS_REQUIRED")
    latest, conflicts, origins = {}, set(), set()
    for row in rows:
        require(isinstance(row, dict), "INCOMPLETE_RAW_ROW")
        require(all(key in row for key in columns if key in {
            "id", "custom_eval_config_id", "trace_id", "observation_span_id", "error",
            "output_bool", "output_float", "output_str", "output_str_list", version,
            "deleted", "_peerdb_is_deleted", "is_deleted",
        }), "INCOMPLETE_RAW_ROW")
        key, revision = identifier(row["id"]), row[version]
        if row["custom_eval_config_id"] is not None and identifier(row["custom_eval_config_id"]) in configs:
            origins.add(key)
        if source["uint64_as_string"]:
            # Existing flag describes JSON 64-bit integer quoting; retain raw
            # rows and decode only the comparison key with declared signedness.
            require(type(revision) is str and revision.isascii()
                    and (revision[1:] if signed and revision.startswith("-") else revision).isdigit(), "VERSION_TYPE")
            revision = int(revision)
        require(key in id_set and type(revision) is int and minimum <= revision < maximum, "VERSION_TYPE_OR_SCOPE")
        previous = latest.get(key)
        if previous is None or revision > previous[0]:
            latest[key] = revision, row
            conflicts.discard(key)
        elif revision == previous[0] and row != previous[1]:
            conflicts.add(key)
    require(set(latest) == id_set, "MISSING_VERSION_HISTORY")
    require(origins == id_set, "ID_DISCOVERY_SCOPE_UNPROVEN")
    require(not conflicts, "LATEST_VERSION_CONFLICT")
    return [item[1] for item in latest.values()], {
        "metadata_sha256": metadata_sha256, "source_sha256": replay.digest(source),
        "id_count": len(ids), "version_count": len(rows), "whole_ids_exhausted": True,
        "whole_versions_exhausted": True,
    }


def flag(row, key, columns):
    value, storage = row[key], columns[key]
    if value is None and key == "deleted" and storage.startswith("Nullable("):
        return False
    require(type(value) is (bool if "Bool" in storage else int) and value in (0, 1), "FLAG_TYPE")
    return bool(value)


def result_value(row, kind, columns):
    if kind == "SCORE":
        value = row["output_float"]
        if value is not None:
            require(finite_number(value), "SCORE_STORAGE")
        return value
    if kind == "PASS_FAIL":
        return None if row["output_bool"] is None else int(flag(row, "output_bool", columns))
    require(type(row["output_str_list"]) is str, "CHOICE_STORAGE")
    try:
        choices = json.loads(row["output_str_list"])
    except (ValueError, TypeError):
        raise replay.ReplayError("REFERENCE_EVAL_CHOICE_STORAGE") from None
    scalar = row["output_str"]
    require(isinstance(choices, list) and all(type(v) is str for v in choices)
            and (scalar is None or type(scalar) is str), "CHOICE_STORAGE")
    return choices + ([scalar] if scalar else []) or None


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def comparison(kind, op, value, fold):
    if op in {"is_null", "is_not_null"}:
        return lambda actual: True
    values = value if isinstance(value, list) else [value]
    require(values and all(v is not None and v != "" for v in values), "OPERAND_REQUIRED")
    if op in {"in", "not_in"}:
        require(isinstance(value, list), "LIST_OPERAND")
    if op in {"equals", "not_equals"}:
        require(not isinstance(value, list), "SCALAR_OPERAND")
    if kind == "SCORE":
        require(all(finite_number(v) for v in values), "SCORE_OPERAND")
        values = [v / 100.0 for v in values]
    elif kind == "PASS_FAIL":
        tokens = {"passed": 1, "pass": 1, "true": 1, "1": 1,
                  "failed": 0, "fail": 0, "false": 0, "0": 0}
        require(all(type(v) in (str, bool, int) and str(v).strip().lower() in tokens for v in values), "PASS_FAIL_OPERAND")
        values = [tokens[str(v).strip().lower()] for v in values]
    else:
        require(all(type(v) is str for v in values), "CHOICE_OPERAND")
    if op in {"equals", "not_equals", "in", "not_in"}:
        def positive(actual):
            return any(v in actual for v in values) if kind == "CHOICE" else actual in values
    elif kind == "SCORE" and op in {"between", "not_between"}:
        require(isinstance(value, list) and len(values) == 2, "RANGE_OPERAND")
        def positive(actual):
            return values[0] <= actual <= values[1]
    elif kind == "SCORE" and op in {"greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal"}:
        require(not isinstance(value, list), "SCALAR_OPERAND")
        compare = {"greater_than": operator.gt, "greater_than_or_equal": operator.ge,
                   "less_than": operator.lt, "less_than_or_equal": operator.le}[op]
        def positive(actual):
            return compare(actual, values[0])
    elif kind == "CHOICE" and op in {"contains", "not_contains", "starts_with", "ends_with"}:
        def lower(text):
            require(text.isascii() or fold is not None, "ENGINE_UNICODE_FOLD_REQUIRED")
            lowered = text.lower() if text.isascii() else fold(text)
            require(type(lowered) is str, "ENGINE_UNICODE_FOLD_REQUIRED")
            return lowered
        needles = [lower(v) for v in values]
        match = {"contains": lambda a, b: b in a, "not_contains": lambda a, b: b in a,
                 "starts_with": str.startswith, "ends_with": str.endswith}[op]
        def positive(actual):
            return any(match(lower(a), b) for a in actual for b in needles)
    else:
        raise replay.ReplayError("REFERENCE_EVAL_OPERATOR_UNSUPPORTED")
    return (lambda actual: not positive(actual)) if op in {"not_equals", "not_in", "not_between", "not_contains"} else positive


def reference_membership(document, scope, leaf, projects, source, read, *, grain, universe=None, fold=None):
    """Return independent target sets; fold, if supplied, must match source lowerUTF8.

    A missing predicate needs a complete independent universe with the same
    grain, metadata_sha256 and scope_sha256. Source certificates are caller
    attestations of actual exhaustion, not a way to bless captured samples.
    """
    require(grain in {"trace", "span"}, "GRAIN_UNSUPPORTED")
    projects = tuple(identifier(p) for p in projects)
    cfg = leaf["filter_config"]
    require(cfg.get("col_type") == "EVAL_METRIC", "FAMILY_UNSUPPORTED")
    require(cfg.get("filter_op") in {"equals", "not_equals", "in", "not_in", "between", "not_between",
        "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal", "contains", "not_contains",
        "starts_with", "ends_with", "is_null", "is_not_null"}, "OPERATOR_UNSUPPORTED")
    configs = resolve_configs(document, scope, leaf["column_id"], projects)
    digest = replay.digest(document)
    _, live, columns = source_layout(source)
    predicates = {key: comparison(v["output_type"], cfg["filter_op"], cfg.get("filter_value"), fold)
                  for key, v in configs.items()}
    rows, evidence = read_latest_eval_rows(configs, source, read, digest)
    matched = set()
    for row in rows:
        config_id = identifier(row["custom_eval_config_id"]) if row["custom_eval_config_id"] is not None else None
        owner = configs.get(config_id)
        if owner is None or any(flag(row, key, columns) for key in live) or flag(row, "error", columns):
            continue
        actual = result_value(row, owner["output_type"], columns)
        trace, span = row["trace_id"], row["observation_span_id"]
        require(trace is None or isinstance(trace, (str, UUID)), "TRACE_TYPE")
        require(span is None or type(span) is str, "SPAN_TYPE")
        if actual is None or trace in (None, "") or str(trace) == str(UUID(int=0)):
            continue
        trace = identifier(trace) if columns["trace_id"] == "Nullable(UUID)" else trace
        require(type(trace) is str, "TRACE_TYPE")
        entity = (owner["project_id"], str(trace))
        if grain == "span":
            if not span:
                continue
            entity += (span,)
        if predicates[config_id](actual):
            matched.add(entity)
    if cfg["filter_op"] == "is_null":
        require(isinstance(universe, dict) and universe.get("complete") is True
                and universe.get("independent") is True and universe.get("grain") == grain
                and universe.get("metadata_sha256") == digest
                and universe.get("scope_sha256") == replay.digest(scope), "COMPLETE_UNIVERSE_REQUIRED")
        entities = universe.get("entities")
        require(isinstance(entities, (list, tuple, set, frozenset)) and all(
            isinstance(e, (tuple, list)) and len(e) == (2 if grain == "trace" else 3)
            and e[0] in projects and all(type(v) is str and v for v in e) for e in entities
        ), "UNIVERSE_SCOPE")
        matched = {tuple(e) for e in entities} - matched
    return matched, {**evidence, "grain": grain, "reference_route": "independent_whole_eval_ids"}
