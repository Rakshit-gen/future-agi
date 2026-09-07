#!/usr/bin/env python3
"""Read scoped eval/annotation metadata via an existing backend pod.

No Django startup, copied credentials, writes, SQL supplied by the caller or
evaluation execution. PostgreSQL enforces READ ONLY on the whole transaction.
The private output contains fixture inputs, not correctness/latency evidence.
"""

import argparse
import json
import subprocess
from uuid import UUID

import replay_observe_filters as replay


REMOTE_PROGRAM = r'''
import collections, datetime, json, os, sys, time
import psycopg
scope = json.loads(sys.argv[1])
projects = json.loads(sys.argv[2])
expected_database = sys.argv[3]
deadline = time.monotonic() + 90
c = psycopg.connect(
    host=os.environ["PGBOUNCER_HOST"],
    port=os.environ.get("PGBOUNCER_PORT", "6432"),
    dbname=os.environ["PG_DB"], user=os.environ["PG_USER"],
    password=os.environ["PG_PASSWORD"], connect_timeout=3,
    application_name="observe-readonly-fixture-discovery",
)
c.read_only = True
try:
    with c.cursor() as q:
        q.execute("SET LOCAL statement_timeout = 5000")
        q.execute("SELECT current_database(), current_setting('transaction_read_only')")
        database, read_only = q.fetchone()
        if database != expected_database or read_only != "on":
            raise RuntimeError("READ_ONLY_DATABASE_IDENTITY_MISMATCH")
        q.execute("""SELECT id FROM tracer_project
            WHERE id = ANY(%s::uuid[]) AND organization_id=%s::uuid
                AND workspace_id=%s::uuid AND NOT deleted""",
            (projects, scope["organization_id"], scope["workspace_id"]))
        if {str(r[0]) for r in q.fetchall()} != set(projects):
            raise RuntimeError("PROJECT_AUTHORIZATION_MISMATCH")
        q.execute("""SELECT c.id, c.project_id, c.eval_template_id,
                    c.name, t.config->>'output', t.output_type_normalized,
                    t.choices, t.deleted
            FROM tracer_custom_eval_config c
            JOIN model_hub_evaltemplate t ON t.id=c.eval_template_id
            WHERE c.project_id = ANY(%s::uuid[]) AND NOT c.deleted
            ORDER BY c.project_id, c.id LIMIT 2001""", (projects,))
        rows = q.fetchall()
        if len(rows) > 2000:
            raise RuntimeError("EVAL_METADATA_INVENTORY_OVERFLOW")
        evals = [dict(zip(
            ("config_id", "project_id", "template_id", "name", "config_output",
             "output_type_normalized", "choices", "template_deleted"), row
        )) for row in rows]
        # Project ids are tracer ids, not Score.project_id (DevelopAI ids).
        q.execute("""SELECT l.id, l.name, l.type, l.settings, l.project_id
            FROM model_hub_annotationslabels l
            WHERE l.organization_id=%s::uuid AND NOT l.deleted
                AND (l.project_id=ANY(%s::uuid[]) OR EXISTS (
                    SELECT 1 FROM model_hub_score s
                    WHERE s.tracer_project_id = ANY(%s::uuid[])
                        AND s.label_id=l.id AND NOT s.deleted
                        AND (s.trace_id IS NOT NULL OR s.observation_span_id IS NOT NULL)
                ))
            ORDER BY l.id LIMIT 501""",
            (scope["organization_id"], projects, projects))
        labels = q.fetchall()
        if len(labels) > 500:
            raise RuntimeError("ANNOTATION_METADATA_INVENTORY_OVERFLOW")
        annotations = []
        for label_id, name, kind, settings, owner_project_id in labels:
            if time.monotonic() >= deadline:
                raise RuntimeError("FIXTURE_DISCOVERY_DEADLINE")
            q.execute("""SELECT DISTINCT s.tracer_project_id
                FROM model_hub_score s
                WHERE s.tracer_project_id=ANY(%s::uuid[]) AND s.label_id=%s
                    AND NOT s.deleted
                    AND (s.trace_id IS NOT NULL OR s.observation_span_id IS NOT NULL)
                ORDER BY s.tracer_project_id""", (projects, label_id))
            label_projects = {str(r[0]) for r in q.fetchall()}
            if str(owner_project_id) in projects:
                label_projects.add(str(owner_project_id))
            q.execute("""SELECT s.tracer_project_id, s.value, s.annotator_id,
                        s.trace_id, s.observation_span_id, s.created_at, s.id, s.updated_at
                FROM model_hub_score s
                WHERE s.tracer_project_id=ANY(%s::uuid[]) AND s.label_id=%s
                    AND NOT s.deleted
                    AND (s.trace_id IS NOT NULL OR s.observation_span_id IS NOT NULL)
                ORDER BY s.updated_at DESC, s.id LIMIT 3""", (projects, label_id))
            examples = [dict(zip(
                ("project_id", "value", "annotator_id", "trace_id", "span_id", "created_at", "score_id", "updated_at"), row
            )) for row in q.fetchall()]
            annotations.append(dict(label_id=label_id, name=name, type=kind,
                settings=settings, project_ids=sorted(label_projects),
                owner_project_id=owner_project_id,
                examples=examples, examples_exhaustive=False))
        # A finite, exhaustive source snapshot is independent truth for CDC
        # parity, including soft-deleted records. Overflow is never sampling.
        q.execute("""SELECT s.id, s.tracer_project_id, s.label_id, s.value,
                    s.annotator_id, s.trace_id, s.observation_span_id,
                    s.created_at, s.updated_at, s.deleted
            FROM model_hub_score s
            WHERE s.tracer_project_id=ANY(%s::uuid[])
                AND (s.trace_id IS NOT NULL OR s.observation_span_id IS NOT NULL)
            ORDER BY s.id LIMIT 10001""", (projects,))
        score_rows = q.fetchall()
        if len(score_rows) > 10000:
            raise RuntimeError("ANNOTATION_SOURCE_SNAPSHOT_OVERFLOW")
        scores = [dict(zip(
            ("score_id", "project_id", "label_id", "value", "annotator_id",
             "trace_id", "span_id", "created_at", "updated_at", "deleted"), row
        )) for row in score_rows]
        print(json.dumps(dict(
            version=2, scope=scope, authorized_projects=projects,
            captured_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            database=database, transaction_read_only=True,
            eval_config_inventory=evals, annotation_inventory=annotations,
            annotation_scores_snapshot=scores, annotation_scores_complete=True,
            annotation_scope="organization-owned live labels owned by authorized projects or referenced by their live trace/span Scores, including organization-wide labels",
            value_examples_are_not_results=True,
        ), default=str, allow_nan=False))
finally:
    c.rollback()
    c.close()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-read-only", action="store_true", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--pod", required=True)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--authorized-projects", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    scope = replay.read_json(args.inventory)["scope"]
    scope = {
        key: str(UUID(scope[key]))
        for key in ("organization_id", "workspace_id", "project_id")
    }
    projects = replay.read_json(args.authorized_projects)
    projects = sorted({str(UUID(project)) for project in projects})
    if scope["project_id"] not in projects or not 1 <= len(projects) <= 100:
        raise replay.ReplayError("INVALID_AUTHORIZED_PROJECTS")
    command = [
        "kubectl",
        "--context",
        args.context,
        "-n",
        args.namespace,
        "exec",
        args.pod,
        "--",
        "python",
        "-c",
        REMOTE_PROGRAM,
        replay.canonical(scope),
        replay.canonical(projects),
        args.expected_database,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=100)
    if completed.returncode:
        # Avoid reproducing driver exceptions/connection details in output.
        raise replay.ReplayError("READ_ONLY_METADATA_DISCOVERY_FAILED")
    document = json.loads(completed.stdout)
    if (
        document["scope"] != scope
        or document["authorized_projects"] != projects
        or document["transaction_read_only"] is not True
    ):
        raise replay.ReplayError("METADATA_PROVENANCE_MISMATCH")
    replay.private_write(args.output, document)
    print(
        replay.canonical(
            {
                "eval_configs": len(document["eval_config_inventory"]),
                "annotations": len(document["annotation_inventory"]),
                "transaction_read_only": True,
                "qualification": "NOT_TESTED",
            }
        )
    )


if __name__ == "__main__":
    main()
