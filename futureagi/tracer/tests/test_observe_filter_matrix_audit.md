# Primary fixture matrix: public-contract audit

> Historical audit checkpoint, not current release status. The subsequent
> implementation and current validation boundaries are summarized in the
> [release checkpoint](../../../docs/qa/observe-optimization-release-checkpoint.md).
> Detailed historical qualification receipts remain local and are not shipped.
> Retained failure classifications below explain the original findings; they
> must not be presented as current failure counts.

Offline source/serializer audit only. No implementation edits, ClickHouse
execution, production queries, or full matrix rerun during concurrent matcher
work. Counts below classify the **previous** 180 SQL + 21 native + 21 grouping
failures; they are not a new full-suite result or 222 independent bugs.

## Public request path, not just builder assumptions

The test harness now uses the actual endpoint serializers:

- Trace list: `TraceObserveListQuerySerializer` ->
  `TraceViewSet.list_traces_of_session` -> `_list_traces_of_session_clickhouse`.
- Session list: `TraceSessionListQuerySerializer` -> `list_sessions`.
- Users list: `UsersQuerySerializer` -> `UsersListManager`.
- Trace/session graphs: `ObserveGraphDataRequestSerializer` /
  `TraceSessionGraphDataRequestSerializer`, followed by `graph_execution_filters`.
- Users **aggregate** graph: `ProjectUsersAggregateGraphDataRequestSerializer`
  -> `get_users_aggregate_graph_data` -> `fetch_user_system_metric_graph_ch`.

Custom leaves carry `property_id=custom_attribute:<key>`. `FilterItemField`
normalizes types/values but does not rename custom keys or change their family.
`validate_property_filter_binding` requires the custom identity, column name,
and `SPAN_ATTRIBUTE` family to agree. Graph preprocessing only consolidates
date bounds. These scalar leaves receive no annotation-principal changes.

Source anchors: `tracer/serializers/filters.py:532`,
`tracer/utils/property_registry.py:227`,
`tracer/services/filter_attestation.py:105`,
`tracer/views/trace.py:4441`, `tracer/views/trace_session.py:1725`,
`tracer/views/project.py:1050`.

Frontend corroboration: `mergeTraceFilterProperties` in
`frontend/src/sections/projects/LLMTracing/TraceFilterPanel.jsx:253` explicitly
retains a raw attribute alongside a same-named System property.
`buildApiFilterFromPanelRow` / `serializeFilterForApi` in
`frontend/src/api/contracts/filter-contract.js:198` preserve the selected field
and family. A legacy SQL promotion is therefore not evidence of a public
custom-to-system mapping. Some old denormalized aliases were intentionally
promoted internally; that intent does not resolve current list/graph divergence.

## Classification of the previous failures

| Previous cases | Classification after API/source audit |
| --- | --- |
| 45 trace-list SQL | 30 root/scope substitutions, 12 raw-key binding substitutions, 3 numeric `span_id` type rejections. Accepted custom requests reach reserved-column dispatch; no public alias conversion found. Keep red. |
| 60 session-list SQL | 45 raw-key substitutions, 9 numeric identifier type rejections, 6 custom `total_cost`/`total_tokens` interceptions by session aggregates. Keep red. |
| 30 trace-graph SQL | Token-semantic aliases / `span_id` and combinations promoted by the SQL dispatcher. The same public custom-token request remains a Map predicate in the exact list compiler. Keep parity/raw-identity failures red. |
| 15 session-graph SQL | 9 numeric identifier type rejections; 6 custom cost/token predicates intercepted as session aggregates. Keep red. |
| 30 Users-aggregate graph SQL | Token-semantic aliases / `span_id` and combinations routed through the shared SQL dispatcher, not renamed by the public serializer. Keep red. |
| 3 native `users:user` | **Harness correction:** UsersView sends `user_id`; the registry explicitly permits that spelling for `system_attribute:users:user`. Test the declared wire adapter, not an assumed catalog-name identity. The 7D corrected case passes. |
| 3 native trace `tags` | Public array filter is accepted, then the scalar attribute dispatcher raises unsupported `array`. `tag` and `tags` are explicitly distinct in the registry; do not invent a `tags -> tag` fix. Keep red as an accepted-but-unsupported path. |
| 9 Users population metrics | `active_users`, `avg_cost_per_user`, `avg_traces_per_user` are graph outputs, not declared per-user output predicates. No public conversion to row metrics exists. Keep red as an **unqualified filter capability**, not proof that their graph computation is broken. |
| 6 global catalog names | `dataset` and `eval_source` are `all`-namespace definitions. No Users per-entity mapping/handler was found. Keep red as an **unsupported routing/capability gap**, not six proven production result defects. |
| 9 session AND grouping | Existing contract test explicitly permits different sibling traces to supply different scalar leaves. List intersects at trace grain, graph at session grain. Keep red. |
| 3 session null grouping | Proven disagreement for **one session with one trace**, one child containing the key and another missing it. Renamed the test to avoid claiming a universal whole-session null policy. Keep the parity failure; deciding the winning null policy remains separate. |
| 9 Users AND grouping | Public aggregate graph applies custom conjunction to each span before user grouping; Users list collects per-key witnesses across spans. No API rewrite removes that distinction. Keep red. This is not a test of the separate user-detail graph endpoint. |

Repeated dates/combinations amplify these counts. Do not describe all 180 SQL
assertions as independently executed ClickHouse result failures. The raw/root
cases expose both historical compatibility behavior and current public-identity
conflicts; any implementation change must preserve explicit System semantics.

## Five highest-priority concrete issues

1. **Accepted typed custom identifiers reach native text dispatch.**
   `SPAN_ATTRIBUTE span_id number greater_than 0.01` passes the trace-list
   request serializer with `custom_attribute:span_id`, then raises
   `UnsupportedFilterShapeError: text column requires a text filter`.
   Session `id` and `span_id` behave similarly. Custom `total_cost` and
   `total_tokens` are additionally intercepted by session aggregate routing.
   Inspect `latest_filter_predicates.py:1686` / `compile_span_filter_plans`,
   `session_list.py:201`, and `exact_graph_reads.py:3130`. Scope: preserve explicit
   custom families before reserved native-field dispatch, not a global alias change.

2. **The same token attribute means different things in list and graph.**
   `SPAN_ATTRIBUTE gen_ai.usage.input_tokens number greater_than 0.01` is a
   latest any-child Map predicate in the trace list, but is promoted to native
   `prompt_tokens` by graph SQL dispatch. A root with zero tokens and a child
   with a positive raw value distinguishes the predicates even if ingestion
   also denormalizes each span's token value. Inspect
   `query_builders/filters.py:1277` / `:1307` and
   `latest_filter_predicates.py:1722`. API normalization leaves the custom
   identity unchanged. Do not conflate this with a SYSTEM_METRIC alias request.

3. **Session AND intersection occurs at different entity grains.**
   One session: trace A supplies key A, trace B supplies key B. The list requires
   both on one trace (`session_list.py:1474`), while the graph groups by session.
   `test_exact_aggregation_contract.py:6650` explicitly asserts the sibling-trace
   contract. Public session serializers preserve both leaves. Graph behavior is
   consistent with that documented existing test; the list is narrower.

4. **Session null parity fails even without multiple traces.**
   For one trace with one key-present child and one missing child, list
   `countIf(exists)=0` rejects; graph `countIf(NOT exists)>0` accepts.
   `session_list.py:225` enables grouped nulls;
   `exact_graph_reads.py:2973` does not, and `:3245` wraps every predicate in
   a positive `countIf`. The API does not normalize nulls differently between
   surfaces. This establishes a mismatch, not which universal null policy to adopt.

5. **Users aggregate graph requires co-location of independent custom leaves.**
   One user: span A supplies key A, span B supplies key B. The Users list's
   collector/matcher can satisfy both; `_user_filter_clauses` ANDs both raw
   predicates inside `candidate_user_spans` before user grouping
   (`exact_graph_reads.py:3557`, `:3790`). The aggregate-graph serializer and view
   pass the same leaves through unchanged. This may omit the user; it also
   warrants checking whether attribute selection incorrectly narrows hydrated
   metrics. No metric-total execution proof was performed here.

Users native-key collection has been changed by main. JSON/negative matcher
work belongs to Volta. Neither was modified or requalified by this audit.

## Limited verification and remaining gaps

- Ran **21 targeted existing cases: 2 passed, 19 failed, 0.61s** after public
  serializer integration. Passing controls: corrected `users:user -> user_id`
  adapter and trace `start_time` intersection. Failures reach the expected
  compiler/routing assertions **after** successful endpoint validation.
- No full-suite count update. No Users collector/matcher tests ran in this
  targeted audit. No skips/xfails introduced; parameter matrix not expanded.
- HTTP authorization/decorators, PostgreSQL metadata, actual ClickHouse truth,
  pagination, remap/tombstone replay, performance, and the separate
  `get_user_graph_data` / `UserDetailTimeSeriesQueryBuilderV2` remain untested.
- The old 6,718-case totals are historical and must not be reported as current
  after concurrent implementation changes. Full integrated rerun is pending.
