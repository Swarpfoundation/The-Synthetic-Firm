import pytest

from synthetic_firm.task import TaskStateError, create_task, transition_task


def test_task_state_transitions():
    task = create_task(title="Build report", objective="Create daily report", created_by_agent_id="atlas")

    task = transition_task(task, "accepted")
    task = transition_task(task, "assigned")
    task = transition_task(task, "in_progress")
    task = transition_task(task, "review_required")
    task = transition_task(task, "completed")

    assert task.status == "completed"


def test_invalid_task_transition_rejected():
    task = create_task(title="Skip states", objective="Try invalid transition", created_by_agent_id="atlas")

    with pytest.raises(TaskStateError):
        transition_task(task, "completed")
