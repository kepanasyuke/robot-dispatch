from __future__ import annotations

import pytest

from robot_dispatch.domain.enums import TaskStatus
from robot_dispatch.domain.policies import RetryPolicy, should_retry
from robot_dispatch.domain.state_machine import (
    InvalidTransition,
    can_transition,
    ensure_transition,
    is_cancellable,
)


class TestTaskStateMachine:
    @pytest.mark.parametrize(
        "current,target",
        [
            (TaskStatus.PENDING, TaskStatus.ASSIGNED),
            (TaskStatus.PENDING, TaskStatus.CANCELLED),
            (TaskStatus.RETRYING, TaskStatus.ASSIGNED),
            (TaskStatus.ASSIGNED, TaskStatus.RUNNING),
            (TaskStatus.ASSIGNED, TaskStatus.SUCCEEDED),
            (TaskStatus.ASSIGNED, TaskStatus.RETRYING),
            (TaskStatus.RUNNING, TaskStatus.SUCCEEDED),
            (TaskStatus.RUNNING, TaskStatus.FAILED),
            (TaskStatus.RUNNING, TaskStatus.RETRYING),
        ],
    )
    def test_allowed_transitions(self, current, target) -> None:
        assert can_transition(current, target) is True
        assert ensure_transition(current, target) is target

    @pytest.mark.parametrize(
        "current,target",
        [
            (TaskStatus.SUCCEEDED, TaskStatus.RUNNING),
            (TaskStatus.FAILED, TaskStatus.PENDING),
            (TaskStatus.CANCELLED, TaskStatus.ASSIGNED),
            (TaskStatus.PENDING, TaskStatus.SUCCEEDED),
            (TaskStatus.PENDING, TaskStatus.RUNNING),
            (TaskStatus.RETRYING, TaskStatus.SUCCEEDED),
        ],
    )
    def test_forbidden_transitions(self, current, target) -> None:
        assert can_transition(current, target) is False
        with pytest.raises(InvalidTransition):
            ensure_transition(current, target)

    def test_terminal_statuses_have_no_exits(self) -> None:
        for status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            assert status.is_terminal is True
            for target in TaskStatus:
                assert can_transition(status, target) is False

    def test_cancellable_statuses(self) -> None:
        assert is_cancellable(TaskStatus.PENDING) is True
        assert is_cancellable(TaskStatus.RETRYING) is True
        assert is_cancellable(TaskStatus.ASSIGNED) is True
        assert is_cancellable(TaskStatus.RUNNING) is False
        assert is_cancellable(TaskStatus.SUCCEEDED) is False


class TestRetryPolicy:
    def test_exponential_growth(self) -> None:
        policy = RetryPolicy(base_delay_seconds=5, max_delay_seconds=100, jitter_ratio=0)
        assert [policy.delay_seconds(attempt) for attempt in (1, 2, 3, 4)] == [5, 10, 20, 40]

    def test_delay_is_capped(self) -> None:
        policy = RetryPolicy(base_delay_seconds=5, max_delay_seconds=12, jitter_ratio=0)
        assert policy.delay_seconds(1) == 5
        assert policy.delay_seconds(5) == 12

    def test_jitter_stays_within_bounds(self) -> None:
        policy = RetryPolicy(base_delay_seconds=10, max_delay_seconds=10, jitter_ratio=0.2)
        for _ in range(50):
            assert 8 <= policy.delay_seconds(1) <= 12

    def test_invalid_attempt(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy().delay_seconds(0)

    def test_should_retry(self) -> None:
        assert should_retry(1, 3) is True
        assert should_retry(2, 3) is True
        assert should_retry(3, 3) is False
        assert should_retry(4, 3) is False
