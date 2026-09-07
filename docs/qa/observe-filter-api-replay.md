# Filter replay: local queries and optional HTTP

The primary validation path is `scripts/qa/replay_observe_queries_readonly.py`:
local candidate queries against the authorized production database, read-only.
It does **not** require a deployed candidate endpoint. See the query-layer
section below. The HTTP runner is an additional layer, not a prerequisite.

`scripts/qa/replay_observe_filters.py` is a standalone Python 3 tool. It imports
neither Django nor a database driver, and never runs migrations or SQL. It calls
the actual allowlisted read APIs using GET and the existing read-only graph /
dashboard-query POST endpoints. It does not save views/widgets/tasks, execute
evals, change data, deploy code, or extract browser credentials.

The implementation/qualification plan is in
[observe-filter-remediation-plan.md](observe-filter-remediation-plan.md).

## Local candidate query replay against production

Use the backend virtualenv with the existing authorized native port-forward.
The runner verifies the expected server and database, blocks Django ORM
connections with the dummy backend, suppresses schema startup, uses only a
process-local cache, and injects a SELECT-only executor into the local query
paths. All referenced project parameters must stay inside the explicit
authorized-project list. Server-enforced read-only and throw-on-overflow
settings are attached to every query. No migrations, table/index changes,
backfill, pods, or cache flushes are performed.

```sh
futureagi/.venv/bin/python scripts/qa/replay_observe_queries_readonly.py \
  --production-read-only --port VERIFIED_NATIVE_PORT \
  --database VERIFIED_DATABASE --expected-server VERIFIED_SERVER_NAME \
  --authorized-projects /private/replay/authorized-projects.json \
  --plan /private/replay/plan.json \
  --surface traces --period 7D --attribute company_id --variant string:in:short \
  --max-cases 3 --run-seconds 300 --safety-seconds 60 \
  --ledger /private/replay/query-results.jsonl
```

Each result records the source fingerprint, query hashes/IDs, client durations,
server execution durations when available, read rows/bytes, completed rows and
independent correctness status. Native-connection and tunnel overhead are
included in replay time; this is not a measurement of deployed API/browser
latency. No candidate endpoint or HTTP token is needed.

`--verify-trace-ids` optionally runs a separate, independent `FINAL` reference
for supported scalar trace filters. Its root population does not use the
candidate's IDs or builders. A proved ordered prefix can verify first-page
IDs/order, but not metrics, HTTP or a transaction-consistent snapshot. Missing
prefix coverage, unsupported semantics or resource stops remain `UNVERIFIED`.
Its time and queries are recorded separately, outside candidate latency.
The scalar trace oracle now supports typed string/number/boolean equality,
negative equality, IN/NOT IN, literal text matching, numeric ordering/ranges,
and null/presence. Ordinary leaves mean a matching latest-live span exists;
negative value leaves require an existing differing value, while `is_null`
means no live span in that trace contains the typed key. Separate leaves can
match different spans. These rules are verified with constant-only truth
tables, not inferred from the candidate query compiler. Picker IN/NOT IN payloads
with explicit `attribute_value_types` now retain each operand's physical Map
type, including homogeneous selections. Numeric-looking strings are not numbers;
false is not zero. Typed NOT IN requires presence of a selected type and no
selected positive value on that same span. Unknown, misaligned or invalid type
tags fail validation. Structured JSON still requires a separate reference.
`--verify-entity-ids` is the preferred alias. With an exhaustive, authorized
`--relational-metadata` snapshot it also checks flat annotation conjunctions:
independent PostgreSQL Score membership followed by ClickHouse `FINAL` roots
for traces, or complete CH25 physical span identities for spans. Span evidence
uses project, trace ID, span ID, UTC replacement hour, observation type and
service name, plus the winning timestamp and version. Trace-only Scores bind
root physical coordinates, not children that reuse the root's external IDs.
Missing identity/version fields are unverified, never a legacy-key fallback.
A separate CDC parity
check is required; neither result proves a shared database transaction. Missing
numeric annotation fixtures and unsupported mixed-family references remain
explicitly unverified.
The reference walks adjacent full-day root intervals newest-first until it has
an independently ordered prefix (up to 250 roots). It discovers complete narrow
primary-index coordinates for each 50-trace batch across all child history,
then runs `FINAL` membership at those coordinates. No attribute/value, deletion,
root-only or child-time predicate can exclude a physical version during that
coordinate discovery. Insufficient prefix coverage cannot prove an empty page.
Earlier company-string IN trace runs matched independent IDs/order for all
three windows on their captured payload/source. Those historical results do
not automatically qualify a new provenance-bearing picker payload or source;
full-row metrics and all other surfaces remain unqualified.

The configured candidate request budget is used, not an invented 8-second
adapter cap and not the requested 5/15/30-second performance targets. Bounded
Trace/Span/Session selector checkpoints are followed without changing the
window, keyset or transport page size; visible-page overflow is buffered.
Missing/non-advancing checkpoints remain errors or incomplete evidence, never
successful empty results. A separate diagnostic wall, byte/memory ceilings,
serial pacing and consecutive-failure circuit breaker protect production.

After the September 4 no-statement-cap clarification, the executor first applies
the same application settings normalization as the native/v2 readers, then
installs **separate diagnostic guards**. Each query record includes both
`application_read_settings` and effective diagnostic `limits`, with
`diagnostic_guards_applied=true`. Explicit application zeros must never zero out
the run's scan/result/memory guards. Legacy selector timeout arguments no longer
act as hidden statement cutoffs in the simulation. Independent reference reads
retain their own run wall and are not included in candidate latency.

`scripts/qa/probe_annotation_operators_readonly.py` provides a separate actual-
engine compiler check using only constant literal rows, not production fixtures
or table scans. It checks numeric JSON type/presence and literal Unicode/text
operations. Run with `--production-read-only`, verified port/server and a new
private output path. A passing literal probe is not customer annotation-filter
qualification or proof of the missing numeric annotation fixtures.

`probe_annotation_candidate_identity_readonly.py` additionally checks candidate
reuse with literal root/child/version/deletion/project-collision rows on the
actual engine. It validates compiler behavior without inserting test records;
it does not replace the independent customer-data identity reference.

After a run, `reconcile_observe_query_memory_readonly.py` accepts its `--ledger`,
verified `--port` / `--expected-server`, `--production-read-only` and a new
private `--output`. It reads only recorded candidate query IDs from
`system.query_log`, never SQL text, and never flushes logs. It records memory,
duration, read rows/bytes, errors and missing IDs; failed queries contribute to
memory peaks. Missing log rows remain unverified because log writes can lag.
Independent reference queries are excluded from candidate resource statistics.
Its own 3s/128MiB diagnostic guards remain separate from application policy.

Source fingerprints include all `tracer` and `tfc` Python sources plus replay
and oracle helpers, including legacy transport policy in `tfc/utils`. Do not
edit those paths during a replay or reuse old-source passes as new qualification.

Trace/span list replay now includes the actual page-scoped content query and
public identity/version merge checks. Trace replay also executes the actual
requested-attribute projection and decoder, preserving typed values. Query-layer
coverage and completed hydration phases are recorded explicitly. The calls run
serially to keep this production diagnostic to one statement in flight; this
is not the public server's parallel scheduling or HTTP timing. Previous
selection-only timings must not be relabeled as hydrated-page measurements.

Limitations: serializers, builders and selectors run locally, but HTTP auth,
signed-cursor encoding, subsequent detail/variable-mapping hydration, PostgreSQL
overlays, eval/annotation cell enrichment and UI rendering are not covered.
Session enrichment queries run
serially in this adapter. Users uses its local manager and exposes any inexact
ordering/count metadata; those fields cannot be relabeled as exact. The local
query runner cannot certify full feature or UI acceptance by itself.

`discover_observe_query_inputs.py` adds real typed catalog suggestions to a
private metadata inventory using bounded, sort-key-prefixed SELECTs. It verifies
the active epoch/revision/build before and after collection, persists a private
resume ledger, and never scans raw spans for input discovery. Up to three
distinct suggestions per name/type are read from at most twelve catalog rows.
Strings are preserved, including numeric-looking identifiers and long text.
Array catalog values represent scalar members: the manifest wraps each member
in a one-element filter list without changing its scalar type. Map/JSON values
are not invented. This does not prove density, all values, history completeness,
or that a suggestion matches the selected date window.

## What it covers

- All discovered custom attribute names and their observed types individually.
- Every canonical valid operator for each declared type, checked against the
  public filter contract. The report retains counts by family/type/operator;
  an unexecuted or unsupported case is never removed from the denominator.
  `select_observe_replay_cases.py --sweep operators --surface SURFACE` selects
  one deterministic real property per family/type across 7D/30D/12M for early
  diagnosis. This canary selection does **not** qualify all properties.
- Fixed 7D / 30D / calendar-12M windows, never a moving `now()` between cases.
- Presence/absence; real-value equality/negation; string contains/multi-value
  membership; numeric greater-than/less-than; array and object operations.
- Real short / long / >500-byte strings when those seeds exist. No truncation
  or coercion of numeric-looking strings. Mixed historical storage types remain
  separate. A dictionary label `json` is treated as a map; ambiguous catalog
  types/absent real seeds are explicitly reported.
- Deterministic 2/5/10-attribute conjunctions across types. Six combinations per
  width by default, plus presence combinations. This is **not every possible
  subset/value/operator permutation** of 242+ attributes.
- Twenty surface variants: Spans/Traces/Sessions, workspace/project Users,
  user-detail Traces/Sessions, four aggregate graphs, Tasks/Eval list previews
  for each entity type, dashboard filters, breakdowns and five numeric metrics.
- Cursor and pending-response chains under one shared diagnostic safety wall.
  Performance targets: **5s lists, 15s graphs, 30s 12M graphs**, as requested.
  These targets are not request timeouts. A timeout,
  sampled result, non-exact ordering, repeated cursor, malformed page or partial
  dashboard metric is not a success. First-page lower-bound totals are recorded
  as such; an exact page does not imply an exact whole-population count.

## Important limits

This is HTTP replay, **not browser-rendering QA**. Tasks/Eval variants exercise
the preview-list stage, not subsequent detail/variable-mapping hydration or eval
execution. Those journeys still require separate tests. A property appearing in
the catalog is not proof that its historical values were backfilled completely.

The discovery command exhausts attribute-name cursors but takes at most the
first 100 suggested values for each attribute, serially. These are request
inputs, not sampled query results. It records `values_complete=false` when more
suggestions exist. It cannot establish production density or rare/long-value
coverage from that page. Add independently verified real seeds and occurrence
evidence before claiming sparse/dense coverage. It never invents missing values.

The requested API target must actually run the local candidate changes and have
authorized production reads. Pointing at today's production build tests the
baseline, not unpushed #2555 changes. `--candidate-label` is just a label. For
verified candidate results, also supply a build header and expected immutable
build identity; every response must match. If the API exposes no build evidence,
the tool deliberately leaves candidate identity unverified.

HTTP/socket work is bounded by an absolute action deadline; name resolution
depends on the host resolver. A local candidate on loopback avoids external DNS
delay. A client timeout stops that HTTP chain, but does **not** prove server-side
async work was cancelled. The runner does not force-refresh or launch parallel
workers; use service/query telemetry to assess any retained server work.

## Run from the PR #2555 worktree

1. Prepare a private scope JSON outside git, containing `organization_id`,
   `workspace_id`, `project_id`, and optionally the actual public `user_id` for
   user-detail tabs. Preserve user IDs as strings. Populate the
   `OBSERVE_REPLAY_AUTHORIZATION` environment variable securely with the full
   Authorization header (for example a scoped Bearer token). Do not paste the
   token into chat, a command argument, report, or committed file.
2. Discover the catalog and actual input values. `API_ROOT` below denotes the
   exact candidate API base URL, including `/api` or version prefix if required.

```sh
python3 scripts/qa/replay_observe_filters.py discover \
  --base-url "$API_ROOT" \
  --scope /private/replay/scope.json \
  --run-seconds 300 \
  --output /private/replay/inventory.json
```

Existing metadata-only inventory JSON can also be used directly for planning.
Its value-dependent cases will be blocked until seeds are supplied. The accepted
attribute format is:

```json
{
  "scope": {
    "organization_id": "AUTHORIZED_ORGANIZATION_ID",
    "workspace_id": "AUTHORIZED_WORKSPACE_ID",
    "project_id": "AUTHORIZED_PROJECT_ID",
    "user_id": "ACTUAL_PUBLIC_USER_ID"
  },
  "attributes": [{
    "name": "ATTRIBUTE_NAME_FROM_CATALOG",
    "property_id": "ACTUAL_PROPERTY_ID_FROM_CATALOG",
    "resolved_type": "string",
    "observed_types": ["string", "number"],
    "seeds": []
  }]
}
```

Each seed is `{"type": "string", "value": "ACTUAL_OBSERVED_VALUE"}` or the
corresponding typed JSON value. Store actual values only in the private manifest.

3. Freeze the plan with one explicit end timestamp:

```sh
python3 scripts/qa/replay_observe_filters.py plan \
  --inventory /private/replay/inventory.json \
  --end 2026-09-05T00:00:00Z \
  --combo-sets 6 \
  --output /private/replay/plan.json
```

To include exact customer-reported predicates such as `agent.duration_s > 1`,
add `--reproductions /private/replay/reported-inputs.json`. The JSON is a list
of `{"label":"reproduction-name","filters":[{"name":"attribute-name",
"type":"number","op":"greater_than","value":1}]}` objects. Names/types must
exist in the inventory; string values stay strings. These are explicitly
reported inputs, not claimed observed catalog values. They generate separate
`reported:<label>` variants in each window/surface, without replacing discovered
seeds or modifying the authorized scope. The DB runner can select them with
`--variant reported:`.

4. Start with one focused reproduction, then bounded batches. Nothing runs in
   the background, and the default is at most 25 cases / five minutes per run.

```sh
python3 scripts/qa/replay_observe_filters.py run \
  --base-url "$API_ROOT" \
  --candidate-label local-pr-2555 \
  --plan /private/replay/plan.json \
  --surface traces --period 7D --attribute company_id \
  --max-cases 25 --run-seconds 300 \
  --ledger /private/replay/results.jsonl \
  --summary /private/replay/summary-01.json
```

Add `--build-header ACTUAL_BUILD_HEADER --expected-build IMMUTABLE_CANDIDATE_ID`
when the endpoint supports this contract. Remove the surface/period/attribute
selectors to cover the remaining planned cases. Increase `--max-cases` only
deliberately; pacing stays serial, and the run stops after three consecutive
failed/stopped actions. `--action-seconds` is a separate diagnostic cap (default
60 seconds, maximum 300); it does not change the performance target or any
application timeout. A correct completion above the target is not aborted.

Resume with the same plan, target, candidate label, oracle and ledger, and a new
summary filename. Completed/failed/blocked actions are skipped unless
`--retry-failed` is explicitly given; retries remain in the ledger. Changes to
plan/target/build/oracle require a new ledger. Ctrl-C preserves completed records;
an interrupted action is not counted. A lock prevents overlapping local runners.
After a crash, verify no runner is active before removing its stale `.lock` file.

For repeated/warm observations, use a **new ledger** with the same fixed plan.
The first request is called first-observed, not guaranteed cold; the runner
records `query_cached` when the server supplies it. It never flushes production
caches or sets forced-refresh flags.

## Correctness and pass conditions

Results contain counts, durations, opaque case IDs and hashes, not raw customer
rows, values or Authorization headers. Private manifests/plans necessarily hold
filter input values. Outputs are created with mode `0600` and never overwritten.
Keep all artifacts outside git.

- `BLOCKED_INPUT`: missing real seed, missing user ID, unsupported request shape
  or unqualified structured breakdown; no HTTP request is made.
- `FAIL`: HTTP/protocol/inexact response or exact-oracle mismatch.
- `SAFETY_STOP`: the diagnostic action wall or continuation-count cap was
  reached. This is not proof of an application failure or an empty population.
- `COMPLETE_UNVERIFIED`: completed HTTP data, but independent correctness and/or
  candidate identity have not both been verified. `latency_met` is separate.
- `API_PASS`: complete result hash matches an independent oracle and candidate
  identity matches. `latency_met` and `performance` independently report whether
  the target was met. A slow correct completion remains correct.
- `NOT_RUN`: still in the plan without an executed/blocked ledger record.

An independent oracle file has `plan_id` plus `cases` keyed by the generated
case ID. Each entry requires `result_sha256` and `provenance` describing the
independent exact reference and consistent population/snapshot. Never copy the
candidate response hash into an oracle and call it independent validation.
The tool verifies provided hashes, **not the honesty or adequacy of their
provenance**. Mutable production records can legitimately drift; investigate a
mismatch against the same population instead of blindly updating expectations.

Hash input uses `canonical()` in the script: sorted JSON keys, compact separators,
ASCII JSON escaping, finite JSON numbers. List input is the ordered accumulated
page; graph input is `{metric_name,data}`; dashboard input is the ordered metrics
projected to `{id,name,aggregation,series}`. Numerical tolerance is not silently
introduced. Oracle generation must explicitly use the same representation or
provide a reviewed comparison instead.

```sh
python3 -m unittest discover -s scripts/qa -p 'test_replay_observe_filters.py' -v
```

These use a temporary local HTTP server and fabricated protocol fixtures. They
validate the runner, not Primary fixture performance or application correctness.
