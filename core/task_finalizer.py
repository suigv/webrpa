from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from core.task_events import TaskEventStore
from core.task_metrics import build_task_metrics_payload
from core.task_store import TaskRecord, TaskStore


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
    ) -> None:
        self._store = store
        self._events = event_store
        self._account_feedback = account_feedback

    def finalize_exception_attempt(self, task_id: str, task_name: str, error: str) -> TaskFinalizeOutcome:
        outcome = TaskFinalizeOutcome()
        with self._store.transaction(immediate=True) as conn:
            self._append_dispatch_result_event(
                conn=conn,
                task_id=task_id,
                task_name=task_name,
                result={"task": task_name, "status": "exception", "ok": False, "checkpoint": ""},
            )
            outcome.retry_record = self._store.schedule_retry(task_id, error=error, conn=conn)
            if outcome.retry_record is not None and outcome.retry_record.next_retry_at is not None:
                self._events.append_event(
                    task_id,
                    "task.retry_scheduled",
                    {
                        "retry_count": outcome.retry_record.retry_count,
                        "max_retries": outcome.retry_record.max_retries,
                        "next_retry_at": outcome.retry_record.next_retry_at,
                        "error": error,
                    },
                    conn=conn,
                )
                outcome.should_enqueue_retry = True
            else:
                current = self._store.get_task(task_id, conn=conn)
                if current is not None and current.cancel_requested:
                    self._store.mark_cancelled(task_id, message="cancelled by user", conn=conn)
                    cancelled = self._store.get_task(task_id, conn=conn)
                    self._events.append_event(
                        task_id,
                        "task.cancelled",
                        build_task_metrics_payload(cancelled, {"reason": "user_exception_path"}),
                        conn=conn,
                    )
                else:
                    self._store.mark_failed(task_id, error=error, conn=conn)
                    failed = self._store.get_task(task_id, conn=conn)
                    self._events.append_event(
                        task_id,
                        "task.failed",
                        build_task_metrics_payload(failed, {"error": error}),
                        conn=conn,
                    )
        return outcome

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
            self._append_dispatch_result_event(conn=conn, task_id=task_id, task_name=task_name, result=result)
            current = self._store.get_task(task_id, conn=conn)
            cancel_requested = bool(current.cancel_requested) if current is not None else False
            if cancel_requested or str(result.get("status")) == "cancelled":
                self._store.mark_cancelled(task_id, message="cancelled by user", conn=conn)
                cancelled = self._store.get_task(task_id, conn=conn)
                self._events.append_event(
                    task_id,
                    "task.cancelled",
                    build_task_metrics_payload(cancelled, {"reason": "user"}),
                    conn=conn,
                )
            elif bool(result.get("ok")):
                self._store.mark_completed(task_id, result=result, conn=conn)
                completed = self._store.get_task(task_id, conn=conn)
                self._events.append_event(
                    task_id,
                    "task.completed",
                    build_task_metrics_payload(completed, {"ok": True}),
                    conn=conn,
                )
            else:
                error = str(result.get("message", "task failed"))
                outcome.retry_record = self._store.schedule_retry(task_id, error=error, conn=conn)
                if outcome.retry_record is not None and outcome.retry_record.next_retry_at is not None:
                    self._events.append_event(
                        task_id,
                        "task.retry_scheduled",
                        {
                            "retry_count": outcome.retry_record.retry_count,
                            "max_retries": outcome.retry_record.max_retries,
                            "next_retry_at": outcome.retry_record.next_retry_at,
                            "error": error,
                        },
                        conn=conn,
                    )
                    outcome.should_enqueue_retry = True
                else:
                    current = self._store.get_task(task_id, conn=conn)
                    if current is not None and current.cancel_requested:
                        self._store.mark_cancelled(task_id, message="cancelled by user", conn=conn)
                        cancelled = self._store.get_task(task_id, conn=conn)
                        self._events.append_event(
                            task_id,
                            "task.cancelled",
                            build_task_metrics_payload(cancelled, {"reason": "user_exception_path"}),
                            conn=conn,
                        )
                    else:
                        self._store.mark_failed(task_id, error=error, result=result, conn=conn)
                        failed = self._store.get_task(task_id, conn=conn)
                        self._events.append_event(
                            task_id,
                            "task.failed",
                            build_task_metrics_payload(failed, {"error": error}),
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
