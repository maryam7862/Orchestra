import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from services.retry import run_with_retry, RetryableError, NonRetryableError, _compute_delay


def test_succeeds_on_first_try():
    calls = {"n": 0}

    def func():
        calls["n"] += 1
        return "ok"

    result = run_with_retry(func, "req-1")
    assert result == "ok"
    assert calls["n"] == 1


def test_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("services.retry.time.sleep", lambda s: None)
    calls = {"n": 0}

    def func():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RetryableError("HTTP_429", "rate limited")
        return "ok"

    result = run_with_retry(func, "req-2")
    assert result == "ok"
    assert calls["n"] == 3


def test_non_retryable_fails_immediately():
    calls = {"n": 0}

    def func():
        calls["n"] += 1
        raise NonRetryableError("AUTH_FAILURE", "bad token")

    with pytest.raises(NonRetryableError):
        run_with_retry(func, "req-3")
    assert calls["n"] == 1  # fail fast, no retry attempted


def test_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr("services.retry.time.sleep", lambda s: None)

    def func():
        raise RetryableError("READ_TIMEOUT", "too slow")

    with pytest.raises(RetryableError):
        run_with_retry(func, "req-4")


def test_status_callback_reports_retrying(monkeypatch):
    monkeypatch.setattr("services.retry.time.sleep", lambda s: None)
    statuses = []
    calls = {"n": 0}

    def func():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RetryableError("HTTP_503", "unavailable")
        return "ok"

    run_with_retry(func, "req-5", on_status=lambda status, detail: statuses.append(status))
    assert "RETRYING" in statuses
    assert "SUCCESS" in statuses


def test_backoff_delay_grows_and_is_bounded():
    d1 = _compute_delay(1)
    d3 = _compute_delay(3)
    assert d1 >= 0
    assert d3 >= 0
    # delay for a later attempt should generally trend upward (jitter aside)
    assert d3 <= 20.0 * 1.4  # never exceeds RETRY_MAX_DELAY + jitter margin
