# Observe type-first delivery plan

Target window: September 5, 2026 20:43 UTC through September 6, 2026 20:43 UTC.
This is a delivery target, not permission to call incomplete work qualified.
Keep changes local in PR #2555's worktree; no production writes, DDL, deployment,
commits or push. Existing qualification evidence remains authoritative and the
full requested feature/type/operator/date/combination scope is unchanged.

## Work order and ownership

| Lane | Work | Owner |
| --- | --- | --- |
| Benchmark coordination | Serial production reads, full25.3 fixtures, frozen snapshots, evidence and integration review | Main |
| Trace execution | Numeric seed and boolean classifier chunking; native latest-state and pagination regressions | Avicenna |
| Text and feature integrations | Long/short text acquisition, shared filter payloads, continuation and incomplete/error vs empty | Lovelace |
| Relational properties | Eval/annotation operators, latest/tombstones, mixed relational and scalar predicates using existing shared compilers | Pasteur |
| Users correctness | Canonical physical-latest activity/order, relation scope and cursor correctness; retain compactness review | Harvey |
| Sessions | Complete positive witness population, canonical group/root ordering and finite relation history | Mendel |
| Graphs/Dashboards | Reuse compact scalar replay, exact aggregate parity and high-cardinality breakdown investigation | Carson |

Agents may work locally in disjoint files. Production reads are coordinated by
the main agent, with one expensive diagnostic in flight. Benchmark an immutable
candidate source snapshot, or freeze the live worktree for the entire cohort.
Use the same scoped read-only credentials, memory protection and separately
labeled diagnostic guards as existing runs.

The first verified Python snapshot is `/tmp/th7247-candidate-snapshot.huMVD4/`:
3,797 application/QA Python files, copied with matching before/after hashes.
The full file manifest binds dependencies outside the narrower replay digest;
`runtime-source-manifest.json` and `runtime-profile-check.json` verify the copied
candidate and its unchanged numeric runtime policy. Environment credentials
and the virtualenv were not copied. The Python-only copy later proved incomplete:
cohort 149 encountered `FileNotFoundError` before issuing SQL in its first three
cases, so it was stopped and supplies no production-query evidence. Runtime
initialization alone did not exercise the missing resource. The missing explicit
runtime asset must be included and hashed in a new snapshot before rerunning;
the original failed snapshot and ledger remain unchanged. An accidentally copied `.uv-cache`
was moved to Trash (original untouched) before runtime validation; the snapshot
is 63 MiB, not a second dependency runtime. Source digest:
`5edaaba87c0d43ca96569c9fcaf6b5ea71bad60cae49763ed8d3f59aa4ae5d41`.
Application initialization passed with sockets denied and the same recorded
runtime policy as cohort 136. This is reproducibility infrastructure, not a
filter pass. Agents can continue work in the original checkout while main
benchmarks the snapshot; later edits require a new snapshot and new evidence.

At the user's request to maximize safe parallelism, all four existing workers
were reactivated at 20:55 UTC. Two additional workers successfully started for
Sessions and Graphs/Dashboards; further creation hit the runtime's thread limit.
The batch error initially obscured those two successful launches; their IDs
and distinct ownership were subsequently recovered. There are six worker lanes,
without a separate-task workaround. Main remains the sole production-query
coordinator. The compactness worker now owns exact Users (separate from
Sessions). Rotate finished workers onto boolean/structured and mixed-type
coverage rather than overlap ownership or multiply cluster load.

## Type-first gates

1. Start with long strings: literal/wildcard/Unicode, sparse/dense/missing,
   positive and negative operators, single/multiple values, then multiple
   long-string properties. Check 7D/30D/12M and each distinct list, graph,
   user-detail, dashboard and preview path; include next/previous pages.
2. Repeat for short strings, numbers, booleans and supported structured fields.
   Local lanes can progress in parallel, but each production cohort has an
   explicit type/operation/surface selection and a frozen source hash.
3. Cover system, eval and annotation property families, including positive
   Secondary fixture annotation cases, not merely empty Primary fixture annotations.
4. Cross the proven families in declared 2/5/10-property combinations. Cover
   long string + annotation + number, multiple values, operator families,
   missing/deleted fields and filter order. Preserve the finite coverage ledger;
   selected combinations are not claimed to be all mathematical permutations.
5. Run the full requested key-coverage sweep and integration regressions on the
   final candidate. A type-level fixture pass does not mark every property or
   feature passed. Missing input, incomplete references, untested full rows,
   pagination and UI behavior remain separately visible.

For every reproduced bug: identify the shared implementation, fix it once,
add a parameterized regression with positive and counterexample rows, and check
other callers for the same failure. Avoid per-account/key special cases,
second query engines and one-off per-screen implementations. Tests and local
benchmark artifacts are accounted separately from deployable code growth.

## Efficient execution without weaker claims

- Group by type, operator family, selectivity, query implementation and scope;
  run the known-failing representatives before expanding their cohort.
- Reuse fixtures and independent reference work where semantics permit. Only
  reuse measured query evidence after proving exact workload equivalence; page
  size, user scope and different aggregation are not interchangeable.
- The v5 exact-request audit found 149,070 distinct unblocked requests and only
  1,938 duplicates, with no cross-surface identical payloads. Shared builders
  alone are therefore not a large measured deduplication opportunity.
- The v6 plan corrects a benchmark omission: text/boolean dashboard metrics use
  supported exact count/count-distinct operations. It retains 157,800 scenarios,
  with 1,668 explicitly blocked cases (780 missing typed values, 810 structured
  breakdowns, 78 structured metrics). These are planned, not executed passes.
- Do not keep increasing code or rerunning a failing broad sweep. Reject a
  slower/incorrect experiment, preserve its evidence, and move the fix to the
  shared path. Review production LOC and redundant paths before handoff.

Lists must remain exact with a 5s target. Graph targets remain 15s, or 30s for
predeclared longest ranges. Targets do not become statement time/row/byte abort
limits. Retain memory safety. No sampling, schema restructuring or production
index creation is authorized in this pass. Proposed index changes require
separate measured justification and approval.

## Current checkpoint

September6 follow-up231: production read-only access restored after GCP login.
Shared read-POST transport is integrated locally (main119 backend/25 wire/169
mounted passes); terminal completed-result corrections pass205 integrated tests.
Session Code184 alias repair passes36 native public-path cases, with2 explicit
Eval/annotation navigation XFAILs still open. The sparse Boolean independent
reference now proves zero eligible IDs after replaying both raw witnesses
(229,0.925s); adaptive-candidate speed is a separate pending gate. Fresh7D
dashboard pair completes4.027s/7.516s, but6 averages differ by tiny Float64
amounts and strict correctness remains unresolved. Users scratch230/232 have7
passes and1 local total-memory failure each, with unchanged cases and caps.
Shared graph physical-latest repair retains224's38 native/24 Session-contract
passes. No whole260-pair/operator/time/surface/pagination qualification asserted.

Follow-ups233–237: adaptive Boolean167 native passes; fresh dense/sparse requests
complete8.670/3.193s, so dense remains a5s miss. Independent sparse reference
again proves zero eligible IDs in0.798s. Users key-presence prototype is rejected:
sparse reads did not decrease, dense diagnostics remain incomplete. Main121FE/
83BE passes validate ten16KiB values under the shared bounded payload contract;
deployed ingress remains unverified. Cached/deprecated terminal fixes pass24
main tests. Initial Eval metadata fails atM0 before candidate SQL; transport/schema
diagnosis remains separate from app correctness. Native235 adds2 Session alias
collision passes; two relational navigation cases still open.

Follow-ups238–243: physical PG name `appdb_prod` verified; using the correct
expected identity restores the scoped metadata capture without production
changes.241 completes a stable Eval-domain observation sequence, with zero
candidate rows in0.384s; independent root/window/page comparison remains open.
The12 read-POST routes exposed a real reader-role403 at custom authentication;
the action-scoped +18-line runtime fix passes50 actual authentication-boundary
tests. Dashboard population diagnostic passes6 native cases but its production
full histogram exceeds the separate result-row safety guard before reference
execution; averages remain unverified. Boolean width-only scratch+7 lines passes
122 native/routing tests, with fresh production pairing pending. No final
matrix, deployed HTTP or whole-feature qualification claim follows.

Follow-ups244–259: existing identity bloom-index definitions are verified, not
their effective use. Users257 exact failed-query counters close the metadata
lane; a smaller ID-discovery replay remains an untested reshape hypothesis.
Boolean251 freshly matches independent ordered IDs for both declared cases:
dense6.362s (miss), sparse2.855s (hit). Session252's two workspace-user relational
cases and four AND controls pass natively after correcting a missing finite
display-store fixture; the full256 wrapper still rejects two intentional
authority errors. A separate source review found numbered-page preflight parity
missing from navigation; repair and full rerun precede integration. Eval258
passes four native positive/empty/drift composition cases after correcting UTC
fixture dates. Production259 matches all21 independent ordered trace IDs in the
explicit April30–May19 root window, with stable before/after owned Eval/root
observations;6.255s remains a5s miss. This is positive Eval ID/order evidence,
not full payload, annotations, all operators or the complete matrix.

Maximum runtime-supported parallelism is **six existing workers plus main**.
The current workers have disjoint worktree ownership or separate scratch-only
prototypes. Completed workers rotate onto the next measured defect; no extra
app threads/worktrees evade the runtime cap. Native25.3 fixture transport and
production SELECTs are main-owned, with one expensive production query at a
time. Experimental code is not promoted merely because its native tests pass.

The 260-pair type-first dossier and 14-case balanced preflight keep the full
coverage denominator explicit. Run181 executed 11: three ID/order matches,
three latency hits, only two with both, and five incomplete/safety-stopped
cases. The other three remain untested. Run186 independently verified two
previously unverified mixed Span empty results at 0.905/1.149s. The single-scan
dashboard prototype passed36 full25.3 fixtures but was not promoted after
27.558s/59.597s production outcomes. Full feature/type/operator/time/positive
data qualification remains open; see the detailed ledger for each limitation.

Latest follow-ups: the separate FINAL-barrier dashboard prototype matched all
30 cells for the unchanged7D query at7.337s, but30D hit the8-GiB diagnostic read
guard and12M the4-GiB memory guard (196). The text-anchor eligibility prototype
also failed its real production case (195), so neither is promoted as a full
fix. Adaptive boolean first50/remaining150/baseline200 passed68 full25.3 tests
(197), awaiting dense/sparse production measurements. Users finite-remap QA
authorization unblocked all six existing cases (198), exposing repeated later
query failures and inexact12M payloads at40–45s. Four shorter empty Users cases
finished2.43–2.68s but have no independent Users oracle. Those earlier missing
PG Eval observations are superseded only by the explicitly scoped241/259
evidence above, not by a whole relational-property qualification.

### Earlier measured checkpoint (preserved)

September6 follow-up: the shared graph latest-window/date-binding repair passed26
full25.3 regressions, including2/5/10 cross-type leaves, after reproducing four
stale-version bugs and missing mixed-filter bindings. The local scalar
text contract fix passed47 backend tests (main rerun) and107 frontend tests;
long-URL delivery is still a separate open gate. The dashboard singleton
prototype passed40 native tests and reduced the7D candidate to5.458s/366MB
reported query memory, but six strict aggregate differences and30D/12M read
safeguard failures keep it unqualified. Adaptive boolean measured7.107s dense
with matching IDs/order, but the sparse case still timed out. Users replay-scope
was rejected after8 semantic native passes because its repeated CTE increased
sparse reads about2×; no production query used that variant. Residual direct
Eval/PG statement caps were removed via the existing shared policy (net−176 app
lines), with118 boundary tests independently rerun. Complete Session navigation
proof remains in progress. A separate boolean raw-primary experiment completed
the sparse case0.543s but without an independent empty proof, and regressed the
dense case17.334s; it is not promoted. No experimental variant is a replacement
for the full matrix, and no production state changed.

Not qualified. Long-text 7D contains completed in 4.648s, but its independent
empty-result reference is insufficient. The numeric primary-seed fix now
finishes the reported greater-than trace case in 1.377s / 0.704s / 3.378s for
7D / 30D / 12M, versus the earlier unfinished roughly 60s root walk. All three
match independent IDs/order, but full rows, pagination and UI are unverified.
The refreshed numeric/long-text local suite passed 130 tests, and the frontend
offline suite passed 404 tests. These do not qualify the full matrix.
Detailed artifacts and historical failed/rejected cohorts remain in the local
qualification log, which is not shipped. See
[the release checkpoint](observe-optimization-release-checkpoint.md) for current
cumulative scope and outstanding validation gates.
