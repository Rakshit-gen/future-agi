"""
v2 VoiceCallList query builder — targets the CH 25.3 spans schema.

Subclass + post-rewrite. Voice calls are LLM agent calls with a specific
attribute shape (call.total_turns, call.talk_ratio, etc.) — these live in
`attrs_number` in v2 (was `span_attr_num` in v1) and are queried heavily
by the voice observability surface. `V2RewriteMixin` routes every inherited
`build*` method's SQL through the v2 rewriter at one boundary.

`build_eval_query` pins the direct-write eval table; `build_annotation_query`
reads `model_hub_score`. Both are excluded from the span-schema token rewrite
because neither query targets `spans`.
"""

from __future__ import annotations

from tracer.services.clickhouse.query_builders.trace_list import TraceListQueryBuilder
from tracer.services.clickhouse.query_builders.voice_call_list import (
    VoiceCallFilterBuilder,
    VoiceCallListQueryBuilder,
)
from tracer.services.clickhouse.v2.query_builders._rewrite import V2RewriteMixin
from tracer.services.clickhouse.v2.query_builders.filters import (
    ClickHouseFilterBuilderV2,
)
from tracer.services.clickhouse.v2.query_builders.trace_list import (
    TraceListQueryBuilderV2,
)


class VoiceCallFilterBuilderV2(ClickHouseFilterBuilderV2):
    """CH25 compiler carrying only the voice-list normalized aliases."""

    VOICE_SYSTEM_METRIC_EXPRS = VoiceCallFilterBuilder.VOICE_SYSTEM_METRIC_EXPRS
    VOICE_SYSTEM_METRIC_STR_MAP = VoiceCallFilterBuilder.VOICE_SYSTEM_METRIC_STR_MAP
    VOICE_SYSTEM_METRIC_STR_EXPRS = VoiceCallFilterBuilder.VOICE_SYSTEM_METRIC_STR_EXPRS


class VoiceCallListQueryBuilderV2(V2RewriteMixin, VoiceCallListQueryBuilder):
    """Drop-in v2 VoiceCallList builder."""

    _v2_rewrite_exclude = frozenset({"build_eval_query", "build_annotation_query"})
    _FILTER_BUILDER_CLS = VoiceCallFilterBuilderV2
    _NORMAL_TIME_WHERE = (
        "AND start_time >= %(start_date)s AND start_time < %(end_date)s"
    )

    def _long_text_candidate_delegate(self) -> TraceListQueryBuilderV2 | None:
        """Reuse CH25's required long-text plan for public voice pages.

        The legacy finite witness is optional and cannot run when application
        reads disable speculative statement caps. Acquire the exhaustive raw
        text candidates first instead. The existing voice classifier still
        decides latest-state membership and the canonical conversation root.
        """
        if (
            self._bounded_internal_scan
            or self._bounded_identity_only
            or self._bounded_sampling_rate is not None
        ):
            return None
        delegate = self._bounded_delegate(
            public_candidate_witness=True,
            trace_builder_cls=TraceListQueryBuilderV2,
        )
        if (
            delegate._positive_exact_end_user_seed_filter() is not None
            or delegate._positive_relational_seed_filter() is not None
            or TraceListQueryBuilder._public_scalar_candidate_seed_plan(delegate)
            is not None
            or delegate._public_long_text_candidate_seed_plan() is None
        ):
            return None
        return delegate

    def supports_filter_candidate_seed_page(self) -> bool:
        return bool(
            super().supports_filter_candidate_seed_page()
            or self._long_text_candidate_delegate() is not None
        )

    def supports_filter_anchor_probe(self) -> bool:
        # A skipped legacy anchor must not replace the required text seed
        # with an unrelated ordered-root scan in the selector's fallback.
        return bool(
            self._long_text_candidate_delegate() is None
            and super().supports_filter_anchor_probe()
        )

    def build_filter_candidate_seed_page(self, **kwargs):
        if super().supports_filter_candidate_seed_page():
            return super().build_filter_candidate_seed_page(**kwargs)
        delegate = self._long_text_candidate_delegate()
        if delegate is None:
            raise ValueError("voice candidate seed is unavailable")
        # Emit legacy tokens through the raw builder, just as the CH25 trace
        # candidate plan does. This voice builder's outer rewrite translates
        # the complete statement exactly once. Child witnesses retain all
        # history; only raw roots are scoped to the requested interval.
        return TraceListQueryBuilder.build_filter_ordered_seed_page(
            delegate,
            **kwargs,
            _positive_scalar_candidate_first=True,
            _restrict_scalar_root_population=True,
        )


__all__ = ["VoiceCallFilterBuilderV2", "VoiceCallListQueryBuilderV2"]
