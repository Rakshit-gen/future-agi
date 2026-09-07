"""Strict equivalence only: do not manufacture coverage by dropping workload."""

from copy import deepcopy

import pytest

from audit_observe_request_equivalence import audit
from replay_observe_filters import ReplayError


def plan():
    case = {
        "id": "first",
        "surface": "traces",
        "target_ms": 5000,
        "window": {"start": "2026-08-01", "end": "2026-09-01"},
        "property_families": ["SPAN_ATTRIBUTE"],
        "blocked": [],
        "request": {
            "method": "GET",
            "path": "/traces/",
            "params": {
                "project_id": "project-a",
                "page_size": 25,
                "filter": {"operator": "in", "values": ["012", "34"]},
            },
            "body": None,
            "target_rows": 25,
        },
    }
    second = deepcopy(case)
    second.update(id="second", surface="another_integration")
    return {"scope": {"workspace": "workspace-a"}, "cases": [case, second]}


def test_identical_requests_report_equivalence_not_execution_or_qualification():
    result = audit(plan(), "a" * 64)
    assert result["total_cases"] == 2
    assert result["exact_request_groups"] == 1
    assert result["cross_surface_groups"] == 1
    assert result["queries_executed"] == 0
    assert result["qualification_status"] == "NOT_EXECUTED"
    assert result["results_may_be_reused_automatically"] is False
    assert "012" not in str(result)  # The artifact contains hashes, not values.


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(path="/sessions/"),
        lambda r: r.update(method="POST"),
        lambda r: r.update(target_rows=1),
        lambda r: r["params"].update(page_size=50),
        lambda r: r["params"].update(project_id="project-b"),
        lambda r: r["params"].update(user_id="scoped-user"),
        lambda r: r["params"]["filter"].update(values=[12, "34"]),
        lambda r: r["params"]["filter"].update(values=["34", "012"]),
        lambda r: r["params"]["filter"].update(operator="not_in"),
        lambda r: r.update(body={"additional_scope": "required"}),
    ],
)
def test_distinct_workloads_cannot_share_a_group(change):
    value = plan()
    change(value["cases"][1]["request"])
    assert audit(value, "a" * 64)["exact_request_groups"] == 2


@pytest.mark.parametrize("field", ["window", "property_families"])
def test_declared_context_is_retained(field):
    value = plan()
    value["cases"][1][field] = ["different"]
    assert audit(value, "a" * 64)["exact_request_groups"] == 2


def test_scope_and_source_are_bound_without_disclosing_payloads():
    first = audit(plan(), "a" * 64)
    second_plan = plan()
    second_plan["scope"]["workspace"] = "workspace-b"
    second = audit(second_plan, "b" * 64)
    assert first["scope_sha256"] != second["scope_sha256"]
    assert first["plan_content_sha256"] != second["plan_content_sha256"]
    assert first["source_sha256"] != second["source_sha256"]
    assert first["groups"][0]["request_sha256"] != second["groups"][0]["request_sha256"]


def test_blocked_case_is_not_relabelled_as_shared_pass():
    value = plan()
    value["cases"][1]["blocked"] = ["missing positive seed"]
    result = audit(value, "a" * 64)
    assert result["blocked_case_ids"] == ["second"]
    assert result["unblocked_cases"] == 1
    assert result["potential_duplicate_requests"] == 0


def test_strictest_target_is_retained_without_becoming_an_abort_limit():
    value = plan()
    value["cases"][1]["target_ms"] = 1000
    assert audit(value, "a" * 64)["groups"][0]["strictest_target_ms"] == 1000


def test_duplicate_ids_fail_closed():
    value = plan()
    value["cases"][1]["id"] = "first"
    with pytest.raises(ReplayError, match="CASE_IDS_MUST_BE_UNIQUE"):
        audit(value, "a" * 64)


def test_embedded_json_strings_are_not_reinterpreted():
    value = plan()
    value["cases"][0]["request"]["params"]["filter"] = '{"values":[12]}'
    value["cases"][1]["request"]["params"]["filter"] = '{"values":["12"]}'
    assert audit(value, "a" * 64)["exact_request_groups"] == 2
