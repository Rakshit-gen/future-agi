"""Executable form of the fetcher ↔ orchestrator contract for Retell polling.

Both sides are built in parallel against the written contract; this file is the
part of it a machine can check, so drift shows up as a failing test instead of
at assembly time. Behavioural cases live in the phase test files.
"""

import dataclasses
import inspect
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest


def _fetcher():
    from tracer.services import observability_providers as m

    return m


def _orchestrator():
    from tracer.utils import observability_provider as m

    return m


class TestFetcherSurface:
    def test_page_dataclass_fields(self):
        m = _fetcher()
        names = [f.name for f in dataclasses.fields(m.RetellPage)]
        assert names == [
            "calls",
            "has_more",
            "next_key",
            "dropped_no_end",
            "dropped_missing",
            "dropped_failed",
        ]
        assert m.RetellPage.__dataclass_params__.frozen

    def test_exception_types(self):
        m = _fetcher()
        assert m.RetellConfigurationError.__bases__ == (Exception,)
        assert m.RetellCursorRejected.__bases__ == (Exception,)
        assert m.RetellCursorRejected(cause="missing_key").cause == "missing_key"

    def test_fetch_signature(self):
        m = _fetcher()
        assert isinstance(
            inspect.getattr_static(m.ObservabilityService, "fetch_retell_page"),
            staticmethod,
        )
        params = list(
            inspect.signature(
                m.ObservabilityService.fetch_retell_page
            ).parameters.values()
        )
        assert [p.name for p in params] == [
            "provider",
            "start_time",
            "end_time",
            "pagination_key",
            "skip",
        ]
        for p in params[3:]:
            assert p.kind is inspect.Parameter.KEYWORD_ONLY
            assert p.default is None

    def test_constants(self):
        m = _fetcher()
        assert m.RETELL_LIST_PAGE_LIMIT == 100  # amendment v1.14 A1: was 1000
        assert m.RETELL_REQUEST_TIMEOUT_SECONDS == 30
        assert m.RETELL_MAX_ATTEMPTS == 3
        assert m.RETELL_HYDRATION_WORKERS == 4  # amendment v1.14 A5
        assert not hasattr(m, "RETELL_CALL_HYDRATION_BOUND")
        assert callable(m._sleep)

    def test_bootstrap_mode_accepts_pagination_key_and_skip(self):
        """A2: the old "pagination_key or skip given in bootstrap mode"
        RetellConfigurationError case is deleted; bootstrap pages under the
        same one-of pagination_key/skip rule as windowed mode."""
        from datetime import UTC, datetime

        m = _fetcher()
        provider = Mock()
        end = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {"items": [], "has_more": False}

        with (
            patch.object(
                m.ObservabilityService,
                "_resolve_retell_key",
                return_value=("k", "agent_x"),
            ),
            patch(
                "tracer.services.observability_providers.requests.post",
                return_value=response,
            ) as mock_post,
        ):
            m.ObservabilityService.fetch_retell_page(
                provider, None, end, pagination_key="k1"
            )
            assert mock_post.call_args.kwargs["json"]["pagination_key"] == "k1"

            m.ObservabilityService.fetch_retell_page(provider, None, end, skip=0)
            assert mock_post.call_args.kwargs["json"]["skip"] == 0

    def test_hydration_pool_is_bounded_by_workers_constant(self):
        """A4: per-item hydration runs through a ThreadPoolExecutor sized by
        RETELL_HYDRATION_WORKERS, not one request at a time."""
        m = _fetcher()
        source = inspect.getsource(m.ObservabilityService._hydrate_retell_calls)
        assert "ThreadPoolExecutor" in source
        assert "RETELL_HYDRATION_WORKERS" in source

    def test_get_call_logs_no_longer_serves_retell(self):
        from unittest.mock import Mock

        from tracer.models.observability_provider import ProviderChoices

        m = _fetcher()
        provider = Mock()
        provider.provider = ProviderChoices.RETELL
        with pytest.raises(NotImplementedError):
            m.ObservabilityService.get_call_logs(provider, None, None)


class TestOrchestratorSurface:
    def test_store_outcome_fields(self):
        m = _orchestrator()
        assert [f.name for f in dataclasses.fields(m.StoreOutcome)] == [
            "stored",
            "malformed",
            "export_failed",
        ]
        assert m.StoreOutcome.__dataclass_params__.frozen

    def test_activity_signature(self):
        m = _orchestrator()
        target = getattr(
            m.fetch_observability_logs, "__wrapped__", m.fetch_observability_logs
        )
        assert list(inspect.signature(target).parameters) == [
            "start_time",
            "end_time",
            "provider_id",
        ]

    def test_fetch_logs_for_provider_signature(self):
        m = _orchestrator()
        sig = inspect.signature(m.fetch_logs_for_provider)
        assert (
            list(sig.parameters)
            == [
                "provider_id",
                "scheduled",
                "start_time",
                "end_time",
                "deadline",  # F1/N1: activity-level deadline, threaded to _poll_retell_provider
            ]
        )
        for name in ("scheduled", "start_time", "end_time", "deadline"):
            assert sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert sig.parameters["deadline"].default is None

    def test_poll_retell_provider_accepts_a_keyword_only_deadline(self):
        """F1/N1: the activity-level deadline is threaded down to
        `_poll_retell_provider` as an optional, keyword-only argument
        defaulting to None (manual runs / direct callers)."""
        m = _orchestrator()
        sig = inspect.signature(m._poll_retell_provider)
        assert "deadline" in sig.parameters
        assert sig.parameters["deadline"].kind is inspect.Parameter.KEYWORD_ONLY
        assert sig.parameters["deadline"].default is None

    def test_state_and_watermark_helpers_exist(self):
        m = _orchestrator()
        for name in (
            "_advance_watermark",
            "_repair_future_watermark",
            "_write_retell_state",
            "_read_retell_state",
            "_page_digest",
            "_parse",
            "_backoff_delay",
            "_hint_for",
            "_classify",
            "_restart_window",
            "_on_total_failure",
            "_log_counts",
            "_log_incomplete",
            "_log_behind",
            "_valid_window",
            "_new_window",  # v1.14 review fix F6
            "_backfill_total_pages",  # v1.14 review fix F4
            "_poll_retell_provider",
            "_manual_retell_run",
            "_poll_other_provider",
        ):
            assert callable(getattr(m, name)), name
        assert not hasattr(m, "_update_last_fetched_at")
        assert not hasattr(m, "normalize_and_store_logs")

    def test_valid_window_rejects_malformed_state(self):
        m = _orchestrator()
        good = {
            "start": "2026-09-03T00:00:00+00:00",
            "end": "2026-09-03T00:10:00+00:00",
            "opened_at_hint": True,
            "narrowed": False,
            "key": None,
            "skip": None,
            "pages_stored": 0,
            "total_pages": 0,
            "digests": [],
            "restarts": 0,
        }
        assert m._valid_window(good)
        assert not m._valid_window({**good, "digests": "notalist"})
        assert not m._valid_window({**good, "start": 12345})
        assert not m._valid_window({**good, "start": "2026-09-03T00:00:00"})
        assert not m._valid_window(
            {**good, "total_pages": "0"}
        )  # v1.14 review fix F1: must be an int
        assert not m._valid_window("nope")

    def test_valid_window_accepts_bootstrap_shape(self):
        """B1: "start": None is a legal bootstrap window, driven by the same
        page loop and the same _valid_window check as an ordinary window."""
        m = _orchestrator()
        bootstrap = {
            "start": None,
            "end": "2026-09-03T00:10:00+00:00",
            "opened_at_hint": False,
            "narrowed": False,
            "key": None,
            "skip": None,
            "pages_stored": 0,
            "total_pages": 0,
            "digests": [],
            "restarts": 0,
        }
        assert m._valid_window(bootstrap)
        assert not m._valid_window(
            {**bootstrap, "end": "2026-09-03T00:00:00"}
        )  # end must still be aware

    def test_restart_window_bootstrap_skips_halving(self):
        """B2: a bootstrap restart uses the same bookkeeping as a windowed
        one, but there is no start to halve — at RETELL_MAX_WINDOW_RESTARTS
        it goes straight to offset mode, and window_hint_seconds is never
        written by a bootstrap restart."""
        m = _orchestrator()
        window = {
            "start": None,
            "end": "2026-09-03T00:10:00+00:00",
            "opened_at_hint": False,
            "narrowed": False,
            "key": "k",
            "skip": None,
            "pages_stored": 3,
            "total_pages": 3,
            "digests": ["d"],
            "restarts": m.RETELL_MAX_WINDOW_RESTARTS - 1,
        }
        state = {"window": window}
        with patch.object(m, "_write_retell_state", return_value=True):
            m._restart_window("pid", state, cause="missing_key")
        assert window["skip"] == 0
        assert window["restarts"] == 0
        assert window["narrowed"] is False  # never halved
        assert "window_hint_seconds" not in state

    def test_restart_window_never_resets_total_pages(self):
        """v1.14 review fix F1 (R1 H1): `total_pages` is the restart-proof
        counter the bootstrap cap is measured against — unlike `pages_stored`,
        `key`, and `digests`, a restart must never reset it."""
        m = _orchestrator()
        window = {
            "start": None,
            "end": "2026-09-03T00:10:00+00:00",
            "opened_at_hint": False,
            "narrowed": False,
            "key": "k",
            "skip": None,
            "pages_stored": 3,
            "total_pages": 7,
            "digests": ["d"],
            "restarts": 0,
        }
        state = {"window": window}
        with patch.object(m, "_write_retell_state", return_value=True):
            m._restart_window("pid", state, cause="missing_key")
        assert window["pages_stored"] == 0  # reset
        assert window["total_pages"] == 7  # NOT reset

    def test_restart_window_bootstrap_offset_stuck_terminates_instead_of_looping(self):
        """v1.14 review fix F1 (R1 H1): a bootstrap whose offset-mode fallback
        also exhausts its restarts must COMPLETE the bootstrap (marker set,
        watermark advanced to the frozen end), not loop `retell_window_stuck`
        forever the way v1.13's windowed stuck branch does."""
        m = _orchestrator()
        window = {
            "start": None,
            "end": "2026-09-03T00:10:00+00:00",
            "opened_at_hint": False,
            "narrowed": False,
            "key": None,
            "skip": 0,
            "pages_stored": 0,
            "total_pages": 5,
            "digests": [],
            "restarts": m.RETELL_MAX_WINDOW_RESTARTS - 1,
        }
        state = {"window": window}
        with patch.object(m, "_complete_bootstrap", return_value=True) as mock_complete:
            m._restart_window("pid", state, cause="missing_key")
        mock_complete.assert_called_once_with("pid", state, m._parse(window["end"]))

    def test_complete_bootstrap_helper_shared_by_completion_and_stuck_paths(self):
        """v1.14 review fix F1: both the normal completion branch and the
        terminal stuck branch must call the SAME `_complete_bootstrap` helper
        so they cannot drift."""
        m = _orchestrator()
        source_poll = inspect.getsource(m._poll_retell_provider)
        source_restart = inspect.getsource(m._restart_window)
        assert "_complete_bootstrap(" in source_poll
        assert "_complete_bootstrap(" in source_restart

    def test_run_budget_loop_exists_and_is_gated_on_the_budget_constant(self):
        """v1.14 review fix F2: `_poll_retell_provider` loops on stored pages
        within RETELL_RUN_BUDGET instead of always returning after one page."""
        m = _orchestrator()
        assert m.RETELL_RUN_BUDGET == timedelta(minutes=20)
        source = inspect.getsource(m._poll_retell_provider)
        assert "while True" in source
        assert "RETELL_RUN_BUDGET" in source

    def test_page_digest_is_a_hash_not_ids(self):
        m = _orchestrator()
        digest = m._page_digest([{"call_id": "call_b"}, {"call_id": "call_a"}])
        assert len(digest) == 64 and "call_a" not in digest
        assert digest == m._page_digest([{"call_id": "call_a"}, {"call_id": "call_b"}])
        assert m._page_digest([]) is None

    def test_constants(self):
        m = _orchestrator()
        assert m.RETELL_VISIBILITY_LAG == timedelta(seconds=60)
        assert m.RETELL_FUTURE_WATERMARK_LOOKBACK == timedelta(hours=1)
        assert m.RETELL_MIN_WINDOW == timedelta(seconds=1)
        assert m.RETELL_BACKOFF_BASE == timedelta(minutes=10)
        assert m.RETELL_BACKOFF_MAX == timedelta(hours=6)
        assert m.RETELL_MAX_FAILED_RUNS == 3
        assert m.RETELL_MAX_WINDOW_RESTARTS == 3
        assert m.RETELL_MANUAL_RUN_MAX_PAGES == 5
        assert m.RETELL_WINDOW_HINT_MAX == timedelta(hours=6)
        assert m.RETELL_WINDOW_GROW_AFTER == 3
        assert m.RETELL_DIGEST_HISTORY == 8
        assert m.RETELL_MAX_PAGES_PER_WINDOW == 50
        assert m.RETELL_BOOTSTRAP_MAX_PAGES == 10  # amendment v1.14 B5
        assert m.RETELL_RUN_BUDGET == timedelta(minutes=20)  # v1.14 review fix F2
        assert m.RETELL_ACTIVITY_BUDGET == timedelta(
            hours=2
        )  # v1.14 review fix F1 (N1)
        assert m.RETELL_BEHIND_WARN == timedelta(minutes=20)
        assert m.RETELL_BEHIND_ERROR == timedelta(hours=6)
        assert m.RETELL_MAX_BACKOFF_EXPONENT == 6
        assert m.RETELL_LIST_PAGE_LIMIT == 100  # amendment v1.14 A1: was 1000

    def test_classify_boundaries(self):
        from tracer.services.observability_providers import RetellPage

        m = _orchestrator()

        def page(failed):
            return RetellPage(
                calls=[],
                has_more=False,
                next_key=None,
                dropped_no_end=0,
                dropped_missing=0,
                dropped_failed=failed,
            )

        assert m._classify(page(0), m.StoreOutcome(0, 0, 0)) == "ok"
        assert m._classify(page(0), m.StoreOutcome(0, 1000, 0)) == "ok"
        assert m._classify(page(0), m.StoreOutcome(0, 1, 999)) == "total"
        assert m._classify(page(0), m.StoreOutcome(0, 999, 1)) == "partial"
        assert m._classify(page(1), m.StoreOutcome(999, 0, 0)) == "partial"

    def test_backoff_never_overflows(self):
        m = _orchestrator()
        assert m._backoff_delay(1) == timedelta(minutes=10)
        assert m._backoff_delay(40) == timedelta(hours=6)
        assert m._backoff_delay(10_000) == timedelta(hours=6)

    def test_poll_state_field_exists_and_is_not_exposed(self):
        from tracer.models.observability_provider import ObservabilityProvider
        from tracer.serializers.observability_provider import (
            ObservabilityProviderSerializer,
        )

        field = ObservabilityProvider._meta.get_field("poll_state")
        assert field.get_internal_type() == "JSONField"
        assert "poll_state" not in ObservabilityProviderSerializer.Meta.fields

    def test_stale_reemit_caveat_is_gone(self):
        m = _orchestrator()
        assert "reuse the same" not in (m._provider_collector_span_id.__doc__ or "")


class TestFixtureShapes:
    def test_list_item_is_lean_and_detail_is_full(self):
        from tracer.tests.fixtures.retell_calls import detail, list_item

        item = list_item("c1", 1_000, 2_000)
        for key in ("transcript", "transcript_with_tool_calls", "recording_url"):
            assert key not in item
        full = detail("c1", 1_000, 2_000)
        for key in (
            "transcript_with_tool_calls",
            "recording_url",
            "call_id",
            "end_timestamp",
        ):
            assert full[key] is not None

    def test_null_timestamp_levers(self):
        from tracer.tests.fixtures.retell_calls import list_item

        assert list_item("c1", None, 2_000)["start_timestamp"] is None
        assert list_item("c1", 1_000, None)["end_timestamp"] is None
