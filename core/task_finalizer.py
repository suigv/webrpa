from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from core.task_events import TaskEventStore
from core.task_metrics import build_task_metrics_payload
from core.task_store import TaskRecord, TaskStore
from core.workflow_drafts import WorkflowDraftService


class AccountFeedbackLike(Protocol):
    def handle_terminal_failure(self, payload: dict[str, Any], error: str) -> None: ...


@dataclass
class TaskFinalizeOutcome:
    retry_record: TaskRecord | None = None
    should_enqueue_retry: bool = False


class TaskAttemptFinalizer:
    def __init__(
        self,
        store: TaskStore,
        event_store: TaskEventStore,
        account_feedback: AccountFeedbackLike | None = None,
        workflow_drafts: WorkflowDraftService | None = None,
    ) -> None:
        self._store = store
        self._events = event_store
        self._account_feedback = account_feedback
        self._workflow_drafts = workflow_drafts

    def _record_workflow_terminal(
        self,
        *,
        task_id: str,
        task_record: TaskRecord | None,
        result: dict[str, Any],
        conn: Any,
    ) -> None:
        if task_record is None or self._workflow_drafts is None:
            return
        workflow_payload = self._workflow_drafts.record_terminal(
            task_record=task_record,
            result=result,
            conn=conn,
        )
        if workflow_payload:
            self._events.append_event(
                task_id,
                "workflow_draft.updated",
                workflow_payload,
                conn=conn,
            )

    def _append_retry_scheduled(
        self,
        *,
        task_id: str,
        retry_record: TaskRecord | None,
        error: str,
        conn: Any,
    ) -> bool:
        if retry_record is None or retry_record.next_retry_at is None:
            return False
        self._events.append_event(
            task_id,
            "task.retry_scheduled",
            {
                "retry_count": retry_record.retry_count,
                "max_retries": retry_record.max_retries,
                "next_retry_at": retry_record.next_retry_at,
                "error": error,
            },
            conn=conn,
        )
        return True

    def _finalize_cancelled_terminal(
        self,
        *,
        task_id: str,
        result: dict[str, Any],
        message: str,
        reason: str,
        conn: Any,
    ) -> None:
        self._store.mark_cancelled(task_id, message=message, conn=conn)
        cancelled = self._store.get_task(task_id, conn=conn)
        self._events.append_event(
            task_id,
            "task.cancelled",
            build_task_metrics_payload(cancelled, {"reason": reason}),
            conn=conn,
        )
        self._record_workflow_terminal(
            task_id=task_id,
            task_record=cancelled,
            result=result,
            conn=conn,
        )

    def _finalize_failed_terminal(
        self,
        *,
        task_id: str,
        error: str,
        result: dict[str, Any],
        conn: Any,
    ) -> None:
        self._store.mark_failed(task_id, error=error, result=result, conn=conn)
        failed = self._store.get_task(task_id, conn=conn)
        self._events.append_event(
            task_id,
            "task.failed",
            build_task_metrics_payload(failed, {"error": error}),
            conn=conn,
        )
        self._record_workflow_terminal(
            task_id=task_id,
            task_record=failed,
            result=result,
            conn=conn,
        )

    def _finalize_completed_terminal(
        self,
        *,
        task_id: str,
        result: dict[str, Any],
        conn: Any,
    ) -> None:
        self._store.mark_completed(task_id, result=result, conn=conn)
        completed = self._store.get_task(task_id, conn=conn)
        self._events.append_event(
            task_id,
            "task.completed",
            build_task_metrics_payload(completed, {"ok": True}),
            conn=conn,
        )
        self._record_workflow_terminal(
            task_id=task_id,
            task_record=completed,
            result=result,
            conn=conn,
        )

    def finalize_exception_attempt(
        self, task_id: str, task_name: str, error: str
    ) -> TaskFinalizeOutcome:
        outcome = TaskFinalizeOutcome()
        terminal_result = {"message": error, "checkpoint": "", "ok": False}
        with self._store.transaction(immediate=True) as conn:
            self._append_dispatch_result_event(
                conn=conn,
                task_id=task_id,
                task_name=task_name,
                result={"task": task_name, "status": "exception", "ok": False, "checkpoint": ""},
            )
            outcome.retry_record = self._store.schedule_retry(task_id, error=error, conn=conn)
            outcome.should_enqueue_retry = self._append_retry_scheduled(
                task_id=task_id,
                retry_record=outcome.retry_record,
                error=error,
                conn=conn,
            )
            if outcome.should_enqueue_retry:
                return outcome
            current = self._store.get_task(task_id, conn=conn)
            if current is not None and current.cancel_requested:
                self._finalize_cancelled_terminal(
                    task_id=task_id,
                    result=terminal_result,
                    message="cancelled by user",
                    reason="user",
                    conn=conn,
                )
            else:
                self._finalize_failed_terminal(
                    task_id=task_id,
                    error=error,
                    result=terminal_result,
                    conn=conn,
                )
        return outcome

    def finalize_cancelled_attempt(
        self,
        *,
        task_id: str,
        task_name: str,
        result: dict[str, Any],
        message: str = "cancelled by user",
        reason: str = "user",
    ) -> None:
        with self._store.transaction(immediate=True) as conn:
            self._append_dispatch_result_event(
                conn=conn,
                task_id=task_id,
                task_name=task_name,
                result=result,
            )
            self._finalize_cancelled_terminal(
                task_id=task_id,
                result=result,
                message=message,
                reason=reason,
                conn=conn,
            )

    def finalize_result_attempt(
        self,
        task_id: str,
        task_name: str,
        result: dict[str, Any],
        payload: dict[str, Any],
    ) -> TaskFinalizeOutcome:
        outcome = TaskFinalizeOutcome()
        feedback_error: str | None = None
        with self._store.transaction(immediate=True) as conn:
            self._append_dispatch_result_event(
                conn=conn, task_id=task_id, task_name=task_name, result=result
            )
            current = self._store.get_task(task_id, conn=conn)
            cancel_requested = bool(current.cancel_requested) if current is not None else False
            if cancel_requested or str(result.get("status")) == "cancelled":
                self._finalize_cancelled_terminal(
                    task_id=task_id,
                    result=result,
                    message="cancelled by user",
                    reason="user",
                    conn=conn,
                )
            elif bool(result.get("ok")):
                self._finalize_completed_terminal(task_id=task_id, result=result, conn=conn)
            else:
                error = str(result.get("message", "task failed"))
                outcome.retry_record = self._store.schedule_retry(task_id, error=error, conn=conn)
                outcome.should_enqueue_retry = self._append_retry_scheduled(
                    task_id=task_id,
                    retry_record=outcome.retry_record,
                    error=error,
                    conn=conn,
                )
                if outcome.should_enqueue_retry:
                    return outcome
                current = self._store.get_task(task_id, conn=conn)
                if current is not None and current.cancel_requested:
                    self._finalize_cancelled_terminal(
                        task_id=task_id,
                        result=result,
                        message="cancelled by user",
                        reason="user",
                        conn=conn,
                    )
                else:
                    self._finalize_failed_terminal(
                        task_id=task_id,
                        error=error,
                        result=result,
                        conn=conn,
                    )
                    feedback_error = error
        if feedback_error is not None and self._account_feedback is not None:
            self._account_feedback.handle_terminal_failure(payload, feedback_error)
        return outcome

    def _append_dispatch_result_event(
        self,
        conn: Any,
        task_id: str,
        task_name: str,
        result: dict[str, Any],
    ) -> None:
        self._events.append_event(
            task_id,
            "task.dispatch_result",
            {
                "task": str(result.get("task") or task_name),
                "status": str(result.get("status") or "unknown"),
                "ok": bool(result.get("ok")),
                "checkpoint": str(result.get("checkpoint") or ""),
            },
            conn=conn,
        )
