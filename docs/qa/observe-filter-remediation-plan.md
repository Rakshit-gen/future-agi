# Observe filter remediation and production-data qualification

## Current acceptance contract

Updated from the user's latest priorities, not the earlier 1/5/10-second gate:

| Priority | Surface | Required result |
| --- | --- | --- |
| P0 | Every list: Spans, Traces, Sessions, workspace/project Users, user-detail Trace/Session tabs; preview list stages | Correct exact first page; **target under 5 seconds total**, including all continuations. No sampling. |
| P0 | Trace/Span/Session/Users graphs and dashboard graphs | Correct exact completed series; **target under 15 seconds total**, or **30 seconds** for predeclared longest-range cases, initially 12M. |
| P1 | Dashboard/graph sampling | Separate opt-in experiment, explicitly approximate, with independently measured error. Not an alternative pass for P0 exact lists. |

No database restructuring. Candidate indexes may be proposed based on measured
query plans; no index build, production write, deployment, or push in this local
pass. Existing unrelated edits must remain intact. All application changes stay
in the worktree associated with PR #2555.

**The target durations are not application failure cutoffs.** A correct slow
completion is recorded as complete with a missed performance target. Do not
introduce a 5/15/30-second timeout or return empty data to meet the targets. The
replay tool has separate, explicit diagnostic safety budgets to protect
production; stopping a diagnostic run leaves the case unqualified, not proven
broken or empty. The latest explicit requirement supersedes the older statement
resource contracts: **remove application statement timeouts and row/byte abort
caps; retain sufficiently high memory safety, concurrency and SQL pagination.**
Request/continuation admission, cancellation and transport failure detection are
separate controls and must be reported, not described as removed statement caps.

### Application memory and statement policy (September 4 clarification)

The native analytics service and v2 readers now share one application read
policy. Old selector timeout arguments no longer become statement execution
deadlines; query time/scan/result row and byte caps are explicitly zeroed.
Memory, thread/concurrency controls, external-sort/group spill thresholds and
SQL pagination are preserved. Direct native maintenance/diagnostic reads and
catalog lifecycle/backfill paths retain their independent guards. A locked
server profile cannot be overridden by application settings.

The memory ceiling is deployment-configurable through
`CLICKHOUSE_APPLICATION_READ_MAX_MEMORY_BYTES` (default **36 GiB**). The v2 path
now honors that same setting instead of its separate hard-coded default.
Zero or oversized per-query memory requests cannot disable/exceed the ceiling;
smaller explicit probe budgets remain meaningful. No production setting changed.

The policy now reaches audited v2 HTTP/native-stream, public catalog and PG
metadata boundaries. HTTP client initialization/connection health stays finite;
application response waiting is not a statement timer. PG uses scoped
`statement_timeout=0` with nested restoration, rather than installing a positive
deadline. Explicit diagnostic contexts cannot inherit an outer application
opt-in. Request/reader-wide budgets and late-response publication checks remain
an open, separate qualification issue; do not mistake them for cancellation or
claim that all end-to-end cutoffs have been removed.

Read-only live capacity check: the selected production pod has a **48 GiB**
container memory limit, a **43.2 GiB** ClickHouse server limit, approximately
**29.6 GiB** tracked consumption and **31.1 GiB** RSS at observation time.
The 36 GiB per-query ceiling is not a reservation or proof of available RAM.
Do not raise it on this evidence: concurrent heavy queries may hit the shared
server limit first. Qualification still needs measured per-query peaks and
concurrent workload headroom. The first historical query-log lookup stopped at
its separate 64 MiB diagnostic scan guard; it supplied no peak-memory evidence.

An earlier exact query-ID reconciliation measured **47.1 MiB peak** across the
90-case annotation span canary (207 successful statements). The still-incomplete
Primary fixture 7D long-text `metadata` case peaked at **64.7 MiB**, including its failed
diagnostic statement, while cumulatively scanning over 609 million rows across
completed statements. These cases do not need a larger memory cap; they establish
neither concurrent server headroom nor sufficiency for the untested largest
graphs. Keep the finite ceiling and optimize the repeated scans. See the dated
qualification ledger for source fingerprints, scope and failed-case accounting.

The latest frozen full-identity replay (September 5, 08:33-08:40 UTC) measured
**212.4 MiB peak** across 207 successful candidate statements after eliminating
repeated span-CTE reads from resolved annotation membership. Its preceding
full-identity version peaked at **422.6 MiB**. All 90 first-page identity/order
references matched; 85/90 finished under 5s, five missed (maximum 5.76657s).
These later measurements supersede the earlier cohort's peak as evidence for
this code path, but still do not qualify the untested largest graphs or imply
36 GiB of free concurrent capacity. Production memory configuration is unchanged.

The later hydrated 16-surface Primary fixture cohort peaked at **1.456 GiB** across
186 recorded statements, including scan-byte/time diagnostic errors. The
five-list follow-up peaked at **1.454 GiB**, again with no memory exception.
Those failures remain scan-work problems, not justification for more memory.
A small subsequent whole-session detail probe returned one trace in **2.528s**
for its aggregate and page queries; the associated list/detail statements peaked
at **81.9 MiB**. This is not largest-session, full-HTTP or concurrent-load
qualification. The finite 36 GiB application ceiling remains high relative to
these observed per-query peaks; untested workloads must still be measured.

## Work sequence

### Operator completeness (explicit user acceptance requirement)

Every supported public type/operator pair is required, not just `equals`:
`not_equals`, `in`/`not_in`, literal `contains`/`not_contains`, prefixes/suffixes,
numeric/date comparisons and ranges, and `is_null`/`is_not_null` where valid.
Use `api_contracts/filter_contract.json` to check applicability; don't invent
unsupported type/operator combinations or silently drop missing input cases.
The replay report now includes `by_property_type_operator` with the full planned,
executed, untested, blocked and independent-identity-match denominator. Mixed
cases count once per operator and do not prove each constituent leaf independently.

`select_observe_replay_cases.py --sweep operators` selects one stable real
property per source/type and every declared operator/value-size variant at
7D/30D/12M. This is a canary execution order, never a replacement for the full
all-property/all-surface matrix. Exact lists are not sampled. Include
multi-annotator/choice cases, missing values, source collisions, empty selection,
literal `%`/`_`/backslash/Unicode and boundary cases in correctness follow-up.

### Cross-property combinations (additional explicit user requirement)

After individual-property/operator/multiple-value checks, qualify combinations
across **both data types and property sources**. Do not count only mixed custom
attributes as mixed-family coverage: system fields, eval outputs and annotations
must participate where each surface supports them. Missing real inputs stay
blocked; do not substitute synthetic production rows.

Before execution, freeze and publish the exact combination manifest and its
coverage denominator. It must distinguish:

- Every supported type/source pair, with positive/negative/presence/range/text
  operations as applicable, and single versus multiple selected values.
- 2/5/10 distinct-property conjunctions covering cross-type/source interactions,
  sparse/dense fields, short/long text and numeric-looking string identifiers.
- Predicate-order variants: reordering an AND must preserve IDs and data;
  selecting multiple values must retain the operator's declared any/all and
  exclusion semantics. Compare against independent references, not just the
  first candidate response.
- Source-name collisions, disjoint/no-match combinations, missing values and
  multi-annotator conflicts, across 7D/30D/12M and all applicable surfaces.

The current six combinations per width are **not exhaustive type/operator
permutation coverage**. Retain them as diagnostic cases only. A full Cartesian
product of all properties, operators and values through width ten is much
larger than a covering matrix; report exactly which interaction orders and
permutations were generated/executed, and never claim that either is the other.
This selects benchmark requests only; it does not sample query results.

### Required property families (not optional)

The September 4 clarification explicitly includes **eval-result properties,
annotations, and every other UI-supported property source**, not just the 242
custom span attribute names. Eval test-preview surfaces are not a substitute for
eval-result filter coverage. Keep separate inventory and coverage denominators
for custom attributes, system/built-in metrics and identities, eval scores and
statuses (including numeric, boolean, categorical/text where supported), and
annotations (labels, scores, annotators and status where exposed).

Discover actual scoped property IDs, types and values, including retired/deleted
and missing-result behavior; do not fabricate IDs or alias a source into
SPAN_ATTRIBUTE. Include same-name collisions across sources and mixed-family
2/5/10-predicate combinations over 7D/30D/12M. Test each property on every
applicable list, graph, dashboard and preview surface. Unsupported routes,
missing metadata, missing fixtures and not-yet-executed cases must be explicitly
reported, not silently excluded. Family completeness is a release gate. The
existing custom-attribute matrix alone **cannot qualify the release**.

1. **Freeze the reproduction matrix and evidence.** Use the authorized Primary fixture
   workspace/project, fixed UTC ends, 7D/30D/12M, and every discovered custom
   attribute individually. Verify the actual inventory rather than substituting
   the user's approximate 250+ count. Keep numbers, strings, booleans, arrays,
   objects and mixed historical types distinct. Include real short/long/>500-byte
   strings and independently identified sparse/dense cases. Add deterministic
   2/5/10-attribute conjunctions and the specific reported filters. This is not
   all mathematically possible combinations; report the exact planned cases.
2. **Reproduce local candidate queries against production read-only.** The user
   confirmed there is no candidate API endpoint. Execute the local serializers,
   builders and selectors with a read-only database adapter; no endpoint or API
   token is required for this layer. Bind every report to its plan, scope and
   source fingerprint. HTTP/auth/UI tests are separate when a candidate endpoint
   becomes available; query-layer success must not be called HTTP E2E success.
   No background load generator, mutating test endpoint or browser credential
   extraction. Separate API wall time, UI rendering and server/cache evidence.
3. **Fix the shared correctness paths locally.** Preserve explicit attribute
   identity and storage type, immutable date/tenant/user scope, latest physical
   record identity, entity-level AND/absence semantics, complete pagination and
   exact error states. A value appearing in a picker is not proof that the list
   predicate or historical population is correct.
4. **Optimize the measured bottleneck.** Separate membership discovery from
   page hydration; push authorized project/time and selective predicates into
   eligible reads, then replay latest state before publishing. Avoid repeated
   full Map materialization and redundant graph scans; consolidate compatible
   dashboard metrics. Preserve deterministic cursors and stable ordering. Do
   not trade away exact results, silently narrow dates, coerce customer IDs,
   return partial totals as exact, or count a timeout as an empty result.
5. **Qualify correctness and latency independently.** Compare returned
   IDs/data/series against an independently obtained exact reference for the
   same scope and snapshot/window. Include deliberately empty, missing-field,
   mixed-type and negative-filter cases. Report cold/first-observed and repeated
   cache-observed runs separately; a first HTTP request does not prove cold
   storage caches. Raise limits only if measured work and correctness justify
   it; a larger timeout is not a speed fix.
6. **Verify the reported UI journeys.** Confirm rows render, filters persist
   correctly, pagination and retry work, and Tasks/Eval preview hydration and
   variable mapping complete. A list-stage API replay alone cannot prove these.
7. **Review before push.** Present changed paths, exact pass/fail/not-run counts,
   latency distributions and remaining constraints. Do not mark the release
   ready until the actual candidate has passed the required production-data
   cases and UI checks.

## Existing local fixes to validate, not assume successful

The qualification report records the current source changes: attribute/native
alias separation, typed filtering, Session and Users entity membership,
latest-state replay, raw date-field attestation, cursor/cache identity fixes,
bounded root discovery, Users graph snapshot reuse, compatible dashboard query
fusion, removal of silent series truncation, preview continuation/error handling
and grid rendering stability.

These passed extensive offline regressions, but several measured production-data
queries still timed out or returned incomplete pages. They are **not yet the
complete performance solution**. The HTTP runner itself has local protocol
tests; those tests are not Primary fixture acceptance results.

## Immediate execution dependencies and gaps

- The live production UI is not evidence that unpushed #2555 changes are running.
  The local query runner is connected read-only to production; HTTP identity,
  auth middleware and browser rendering remain separate unverified layers.
- The verified inventory contains 242 custom names / 260 observed name-type
  pairs. Bounded catalog discovery has supplied inputs for 247 pairs; 13
  numeric pairs still lack a seed. Forty-four real string inputs exceed 500
  bytes (largest 16,264 bytes). Suggestions do not establish live membership,
  density or historical completeness. Explicitly reported user predicates
  are tracked separately from catalog-derived values.
- Independent exact expected results and population-density evidence are not
  available for the whole matrix. API completions remain correctness-unverified
  until matched to an independent oracle.
- Current replay coverage for Tasks/Evals is the list stage only. Full detail
  hydration, variable mapping, UI rendering and eval execution are not implied.
- Index changes and a sampled graph path need their own measured validation;
  neither has been applied by this plan.

## Sampling experiment gate (P1 only)

Investigate sampling only after preserving the exact P0 path. Specify stable
sampling units, deterministic inclusion, time/filter coverage and treatment of
rare groups. Compare count/sum/mean/percentiles/grouped results independently;
one scale factor cannot make every aggregate accurate. Require displayed
approximation metadata and measured error bounds before proposing a default.
Never use sampled rows for entity-list membership, exact totals, task selection
or evaluation input selection. No accuracy guarantee is currently established.
