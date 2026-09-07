# Cumulative Observe optimization checkpoint

Status: **assembled for review, not production-performance qualified**.

This branch is based on main `2d244e6b0566f265337c42ea50299dc5f0dbf96e`.
It preserves the published task-filter hotfix `e9b1f9ee8` and the retained
Observe optimization worktree delta. At the user's request, the separate
collector/catalog compatibility changes from `717ff4448` are excluded from
this PR's net diff. PR #2555 remains unchanged; this PR therefore no longer
supersedes its catalog/runtime compatibility changes.

## Included

| Area | Retained implementation |
| --- | --- |
| Trace and span lists | Candidate acquisition using physical coordinates and indexed prefixes; scalar, numeric, boolean and text witnesses; latest-version replay; adaptive acquisition and refill; cursor and hydration changes. |
| Sessions and users | Exact entity and alias membership, latest-state handling, activity cursors, page-scoped metrics and hydration, numeric session-graph witness and absence handling. |
| Graphs and dashboards | Exact filter membership and root discovery, numeric trace-graph candidates, physical snapshot reuse and aggregation changes. No new sampling behavior is enabled by this assembly. |
| Filters and task/eval previews | Typed source precedence, native versus raw identifiers, mixed-value preservation, AND-preserving task serialization, physical detail context, continuation and loading ownership. |
| Read transport | Server-marked read POST with authentication and tenant checks; native compression dependencies; application time/row/byte statement-policy changes with memory safety retained. This is not proof that all deployment or infrastructure cutoffs are absent. |
| Qualification tooling | Reusable replay planners, independent references, hydration/timing and memory checks, property inventory and associated regression tests. |

The retained Observe source delta is included, including its formerly untracked
helpers and tests. Rejected or unapplied scratch experiments are not promoted.
Production payloads, signed cursors, credentials, local runners, and test-output
artifacts are not included. Two historical QA logs remain in the original
worktree; this checkpoint supersedes them for release-scope reporting.

### Scope cleanup

The following eight files are restored byte-for-byte to the PR's main baseline:

- `fi-collector/pkg/propertycatalog/producer_retirement.go` and its Go test.
- Catalog `durable_lifecycle.py`, `projection.py` and `reconciler.py`.
- Their three physical-snapshot, projection and reconciliation test files.

This excludes the separate producer-retirement, physical-snapshot lifecycle and
cross-revision reconciliation fixes. No collector build, image or configuration
change is included in this PR. Catalog read-connection policy changes remain
because they support Observe property pickers. Query, filter, graph, dashboard,
task/eval, pagination, hydration, transport and benchmark changes are retained.
The excluded fixes remain recoverable in commit `717ff4448` and PR #2555; they
are not deleted from history, and this cleanup does not change production data.

Cleanup verification: all eight restored files match main exactly; the other
Observe implementation and test files are unchanged from `016593ca4`. The three
restored Python test modules pass **41 tests** with default settings, repository
startup/conftest disabled, no configured database and network access blocked.
This focused check does not clear the existing CI or performance gates below.

## Assembly corrections

- Preserve the published legacy span-ID fallback alongside canonical trace/session
  filter handling.
- Preserve missing-source legacy session-ID task filters through hydration and
  round trips; explicit raw metadata still wins.
- Prevent explicit eval/annotation properties with native-looking names from
  being dispatched as native columns or time-window predicates.
- Keep Users-grid loading owned by active requests in the current generation.
- Supply explicit nullable navigation response serializers and synchronize the
  physical span-detail and read-POST generated contracts.
- Correct test lint without dropping assertions, fixture registrations or cases.

## Fresh local evidence

These groups overlap and must **not** be summed into a unique-case count.

| Check | Result and boundary |
| --- | --- |
| Frontend regression selection | 2,721 passed, zero failed/pending, 198 test files; source unchanged during the full run. |
| Final test-mock lint correction | Six affected mounted tests passed again after the lint-only mock correction. |
| Production-mode frontend build | Passed using Node 22.18.0; final frontend source unchanged during the build. Network was denied, including source-map upload attempts. Warnings remain. |
| Generated API contracts | Contract checks passed, including coverage thresholds; no baseline thresholds relaxed. |
| Read policy/transport | 495 portable tests passed; DB-marked and deliberate loopback tests excluded. |
| Read POST/auth/navigation contract | 147 passed, including seven new navigation serializer cases; four DB-marked exclusions. |
| Trace/span portable checks | 226 passed at their recorded source revision; subsequent shared date-dispatch correction was tested separately. |
| Session graph portable checks | 67 passed; not a Session-list or full API qualification claim. |
| Explicit-source/date regression | 101 passed after the date-dispatch correction. |
| Three compiler/membership suites | 373 passed, 22 failed; remaining failures classified below. |
| Backend test-file maintenance selection | 781 passed, six failures reproduced before lint edits; 190 native/integration/DB cases not executed in this portable run. |
| Isolated ClickHouse graph fixtures | 11 passed, zero failed/skipped; ClickHouse 25.3.14.14 in a network-isolated container. Owned fixture databases cleaned up. This preceded the final shared date-dispatch correction. |
| QA replay/reference guards | 93 tests plus 86 subtests passed with network denied. |

The original worktree was hash-audited and remains unchanged. The main-based
assembly and all validation receipts have separate local locations.

## Outstanding release and performance gates

1. **Required CI checks:** the previously pushed `5ac90b3` has failing backend
   shards, backend schema generation, frontend integration and E2E checks. Local
   fixes below do not clear those gates until CI reruns successfully.
2. **Six Session navigation tests:** failures reproduce with their pre-lint tests;
   mock response-shape and old query/no-query expectations require reconciliation
   and rerun. They are not counted as passing.
3. **Private EE schema parity:** the offline backend schema generator does not
   contain 73 private routes. Those existing routes were preserved. Shared
   generated routes and serializers were refreshed; the full private-EE schema
   generation still needs CI validation.
4. **Production qualification remains open:** this assembly does not prove all
   Primary fixture properties/operators/multi-value and cross-type combinations over
   7D, 30D and 12M, positive Secondary fixture annotation cases, populated next/previous
   navigation, or all list/graph/dashboard surfaces.
5. Performance targets remain targets, not hard query-failure thresholds:
   lists under five seconds; graphs under fifteen seconds, with up to thirty
   seconds for exceptionally large requests. Full independent Users oracle
   validation, populated long-window Session graph latency and large dashboard
   completion remain unresolved.

No deployment, image update, production query, database backfill, schema/index
change or production restart is performed by this assembly checkpoint.

## Review follow-up (2026-09-07)

- User graph annotation/eval null and negative filters now use whole-user
  membership, matching the list semantics. A missing/nonmatching sibling does
  not prove absence of a forbidden value elsewhere on the user.
- Initial task/eval preview requests no longer have the client-side hard wall
  that discarded slow valid responses. Explicit cancellation and resumable
  continuation handling remain.
- Session-detail navigation uses a validated read-POST alias so large filter
  context travels in the body. Legacy detail GET remains available and both
  paths share authentication, tenant scoping and detail retrieval. Deploy the
  backend alias before or together with its frontend caller.
- Generated schema, clients and contract reports include the new route without
  dropping existing routes or relaxing coverage requirements.
- Session membership/witness assertions now cover the combined stage while
  retaining independent-leaf, tenant, root-presence and pre-pagination checks.
- Call-log tests expose the existing read-query mock; the E2E filter-response
  waiter recognizes POST bodies as well as legacy GET query parameters.

Fresh offline selection after these edits: **198 backend tests passed** across
four modules and **117 frontend tests passed** across five files. These are
focused regressions, not production benchmarks or complete CI qualification.
Native database and live API checks are not represented by these counts.

The follow-up regression correction updates old publication-timeout expectations
to preserve completed responses while retaining admission/error handling. It
also uses real builder helpers in org-scope mocks, complete physical identities
in content fixtures, literal eval-text operators, typed boolean hydration and
compiler-proven raw-prefix replay assertions. No test is removed or CI gate
disabled. The combined final offline selection passed **444 backend tests**;
15 native-database cases were excluded by the local harness, not by repository
or CI configuration. This replaces, rather than adds to, the 198-test tally.

CI on `05d01e8ce` passed frontend contracts but still failed the backend Swagger
generation step. That workflow suppresses its failure log to protect private EE
source. A sanitized generation error from the matching EE checkout is needed
to diagnose it without exposing private source or dropping existing contracts.
Other backend regression failures outside the focused selection remain open.


## CI recovery checkpoint (2026-09-07, after `68c79f35a`)

The 60 explicit failing cases extracted from Backend CI run `34096392251`
passed together against verified local ClickHouse 25.3.14.14, PostgreSQL and
Redis: **60 passed**, three warnings, 12.92 seconds. Three canceled shards
did not finish, so their unseen cases remain unqualified. These results do
not replace a green full CI run on the new commit.

Session navigation now validates the originating sort before canonical-ID
lookup. Dashboard reads preserve a complete exact payload when final
formatting crosses the timing target. Regression fixtures retain membership,
tenant, pagination and tombstone checks while matching the current physical
replacement identity, session-level nullness and versioned snapshot paths.

The full schema was regenerated with the exact EE revision used by CI,
`7447f2ae6e7dc2ec61731efa5df9e0bb5cb8b4fc`. All 987 API paths match; only an
unreferenced response definition was removed, integer bounds were restored to
the generator output, and response-key ordering was synchronized. Repeated
generation was byte-identical. Frontend contract checks passed, with no net
changes to generated clients and no relaxation of the surface-shrink guard.

Matrix artifacts and customer-specific fixture labels now use generic names.
All 6,718 renamed matrix cases collect; collection is not an executed pass.
Replay-memory checks pass. The earlier navigation and local EE-generation
blockers above are resolved by these receipts, while remote CI and the full
production-data correctness/performance matrix remain open. Deployment
readiness is **not established**.


## Remaining dashboard CI regressions (2026-09-07, after `2ad4ff58f`)

The next CI run exposed three stale assertions across the public dashboard
legacy-filter path and both modes of the grouped metric test. The public test
now exercises the real exact-snapshot compiler, retaining the legacy-filter
normalization checks. Grouped metrics still verify all 257 series and now
assert three fresh read budgets plus the collection fence.

A complete local run also reproduced a hang in three old dashboard/widget
refresh tests: an unspecified scheduler mock was being serialized recursively.
Those fixtures now return concrete pending responses and require one cache
probe followed by one refresh for the same identity, without inline analytics.
No application behavior or CI gate was changed.

Both affected modules completed against attested local test services:
**599 passed, 29 skipped**, three warnings, 14.72 seconds. The skips remain
unqualified. The earlier CI runner shutdowns did not include completed failure
reports, so their cause and the full remote result require the new CI run.
