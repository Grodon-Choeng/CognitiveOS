from app.infrastructure.temporal.workflows.reminder_workflow import ReminderWorkflowState


def test_reminder_workflow_state_defaults() -> None:
    state = ReminderWorkflowState()

    assert state.reminder_id == ""
    assert state.status == "pending"
    assert state.last_reply_text is None
    assert state.reply_received is False
