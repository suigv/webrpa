from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Protocol

from core.account_feedback import AccountFeedbackService
from core.task_events import TaskEventStore
from core.task_queue import QueueBackend, create_task_queue
from core.task_store import TaskRecord, TaskStore
from core.device_manager import DeviceManager
from engine.runner import Runner
from engine.plugin_loader import PluginLoader


class RunnerLike(Protocol):
    def run(self, script_payload: dict[str, Any], should_cancel: Any = None) -> dict[str, Any]: ...


class AccountFeedbackLike(Protocol):
    def handle_terminal_failure(self, payload: dict[str, Any], error: str) -> None: ...


class TaskController:
    def __init__(
        self,
        store: TaskStore | None = None,
        queue_backend: QueueBackend | None = None,
        runner: RunnerLike | None = None,
        event_store: TaskEventStore | None = None,
        account_feedback: AccountFeedbackLike | None = None,
    ) -> None:
        self._store = store or TaskStore()
        self._queue = queue_backend or create_task_queue()
        self._runner = runner or Runner()
        self._events = event_store or TaskEventStore()
        self._account_feedback = account_feedback or AccountFeedbackService()
        self._device_manager = DeviceManager()
        self._plugin_loader = PluginLoader()
        self._plugin_loader.scan()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        
        # 并发线程池，最大并发数可以根据云机数量动态调整，默认给 32
        import concurrent.futures
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._recover_stale_running_tasks()
        
        import concurrent.futures
        max_workers = int(os.environ.get("MYT_MAX_CONCURRENT_TASKS", "32"))
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, 
            thread_name_prefix="task-worker"
        )
        
        self._worker = threading.Thread(target=self._work_loop, name="task-controller-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._executor is not None:
            self._executor.shutdown(wait=False)
        if self._worker is not None:
            self._worker.join(timeout=2)

    def submit(self, payload: dict[str, Any], devices: list[int], ai_type: str) -> TaskRecord:
        task_id = str(uuid.uuid4())
        self._store.create_task(
            task_id=task_id,
            payload=payload,
            devices=devices,
            ai_type=ai_type,
            idempotency_key=None,
            max_retries=0,
            retry_backoff_seconds=2,
            priority=50,
            run_at=None,
        )
        self._queue.enqueue(task_id, priority=50)
        self._events.append_event(
            task_id,
            "task.created",
            {"priority": 50, "run_at": None, "max_retries": 0, "retry_backoff_seconds": 2},
        )
        record = self._store.get_task(task_id)
        if record is None:
            raise RuntimeError("failed to create task")
        return record

    def submit_with_retry(
        self,
        payload: dict[str, Any],
        devices: list[int],
        ai_type: str,
        max_retries: int,
        retry_backoff_seconds: int,
        priority: int,
        run_at: str | None,
        idempotency_key: str | None = None,
    ) -> TaskRecord:
        record, created = self._store.create_or_get_active_task(
            payload=payload,
            devices=devices,
            ai_type=ai_type,
            idempotency_key=idempotency_key,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            priority=priority,
            run_at=run_at,
        )
        if not created:
            self._events.append_event(
                record.task_id,
                "task.duplicate_submit_ignored",
                {"idempotency_key": idempotency_key},
            )
            return record

        task_id = record.task_id
        delay = 0
        run_at_epoch: float | None = None
        if run_at:
            run_at_epoch = self._iso_to_epoch(run_at)
            delay = self._delay_seconds(run_at)
        self._queue.enqueue(task_id, delay_seconds=delay, priority=priority, run_at_epoch=run_at_epoch)
        self._events.append_event(
            task_id,
            "task.created",
            {
                "priority": priority,
                "run_at": run_at,
                "idempotency_key": idempotency_key,
                "max_retries": max_retries,
                "retry_backoff_seconds": retry_backoff_seconds,
            },
        )
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        return self._store.get_task(task_id)

    def list(self, limit: int = 100) -> list[TaskRecord]:
        return self._store.list_tasks(limit=limit)

    def list_events(self, task_id: str, after_event_id: int = 0, limit: int = 200):
        return self._events.list_events(task_id=task_id, after_event_id=after_event_id, limit=limit)

    def cancel(self, task_id: str) -> bool:
        result = self._store.request_cancel(task_id)
        return result in {"cancelled", "cancelling"}

    def cancel_state(self, task_id: str) -> str | None:
        state = self._store.request_cancel(task_id)
        if state is not None:
            self._events.append_event(task_id, "task.cancel_requested", {"state": state})
            if state == "cancelled":
                self._events.append_event(
                    task_id,
                    "task.cancelled",
                    self._metrics_payload(task_id, {"reason": "user_pending"}),
                )
        return state

    def clear_all(self) -> None:
        """Wipe all tasks from store and clear the execution queue."""
        self._store.clear_all_tasks()
        # Note: Depending on backend, clear might not be supported on all QueueBackend.
        # But we attempt to clear the store first which is the source of truth.
        # Re-initialize the queue if possible or let the dequeue fail gracefully.
        try:
            # Most backends used in this project support a simple clear or re-init
            self._queue = create_task_queue()
        except Exception:
            pass

    def task_metrics(
        self,
        window_seconds: int = 3600,
        failure_rate_threshold: float = 0.2,
        cancellation_rate_threshold: float = 0.2,
        min_terminal_samples: int = 20,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(seconds=max(0, int(window_seconds)))
        since_iso = since.isoformat()
        event_counts = self._events.count_by_type(since=since_iso)
        status_counts = self._store.status_counts()
        terminal_outcomes = {
            "completed": int(event_counts.get("task.completed", 0)),
            "failed": int(event_counts.get("task.failed", 0)),
            "cancelled": int(event_counts.get("task.cancelled", 0)),
        }
        terminal_total = max(0, sum(int(v) for v in terminal_outcomes.values()))
        completion_rate = float(terminal_outcomes["completed"]) / terminal_total if terminal_total > 0 else 0.0
        failure_rate = float(terminal_outcomes["failed"]) / terminal_total if terminal_total > 0 else 0.0
        cancellation_rate = float(terminal_outcomes["cancelled"]) / terminal_total if terminal_total > 0 else 0.0

        threshold_failure = min(1.0, max(0.0, float(failure_rate_threshold)))
        threshold_cancel = min(1.0, max(0.0, float(cancellation_rate_threshold)))
        min_samples = max(1, int(min_terminal_samples))
        evaluated = terminal_total >= min_samples
        reasons: list[str] = []
        if evaluated and failure_rate >= threshold_failure:
            reasons.append("failure_rate_exceeded")
        if evaluated and cancellation_rate >= threshold_cancel:
            reasons.append("cancellation_rate_exceeded")

        return {
            "generated_at": now.isoformat(),
            "window_seconds": max(0, int(window_seconds)),
            "since": since_iso,
            "status_counts": status_counts,
            "event_type_counts": event_counts,
            "terminal_outcomes": terminal_outcomes,
            "rates": {
                "completion_rate": completion_rate,
                "failure_rate": failure_rate,
                "cancellation_rate": cancellation_rate,
            },
            "alerts": {
                "evaluated": evaluated,
                "triggered": bool(reasons),
                "reasons": reasons,
                "thresholds": {
                    "failure_rate": threshold_failure,
                    "cancellation_rate": threshold_cancel,
                    "min_terminal_samples": min_samples,
                },
                "terminal_total": terminal_total,
            },
        }

    def task_metrics_prometheus(
        self,
        window_seconds: int = 3600,
        failure_rate_threshold: float = 0.2,
        cancellation_rate_threshold: float = 0.2,
        min_terminal_samples: int = 20,
    ) -> str:
        metrics = self.task_metrics(
            window_seconds=window_seconds,
            failure_rate_threshold=failure_rate_threshold,
            cancellation_rate_threshold=cancellation_rate_threshold,
            min_terminal_samples=min_terminal_samples,
        )

        lines = [
            "# HELP new_task_status_count Current task count by status.",
            "# TYPE new_task_status_count gauge",
        ]
        status_counts = metrics.get("status_counts", {})
        for status in sorted(status_counts):
            lines.append(
                f'new_task_status_count{{status="{self._prometheus_escape(str(status))}"}} {int(status_counts[status])}'
            )

        lines.extend(
            [
                "# HELP new_task_event_type_count Task event count by event type within window.",
                "# TYPE new_task_event_type_count gauge",
            ]
        )
        event_type_counts = metrics.get("event_type_counts", {})
        for event_type in sorted(event_type_counts):
            lines.append(
                f'new_task_event_type_count{{event_type="{self._prometheus_escape(str(event_type))}"}} {int(event_type_counts[event_type])}'
            )

        lines.extend(
            [
                "# HELP new_task_terminal_outcome_total Task terminal outcomes within window.",
                "# TYPE new_task_terminal_outcome_total gauge",
            ]
        )
        terminal_outcomes = metrics.get("terminal_outcomes", {})
        for outcome in sorted(terminal_outcomes):
            lines.append(
                f'new_task_terminal_outcome_total{{outcome="{self._prometheus_escape(str(outcome))}"}} {int(terminal_outcomes[outcome])}'
            )

        rates = metrics.get("rates", {})
        lines.extend(
            [
                "# HELP new_task_completion_rate Completion rate in terminal outcomes window.",
                "# TYPE new_task_completion_rate gauge",
                f'new_task_completion_rate {float(rates.get("completion_rate", 0.0))}',
                "# HELP new_task_failure_rate Failure rate in terminal outcomes window.",
                "# TYPE new_task_failure_rate gauge",
                f'new_task_failure_rate {float(rates.get("failure_rate", 0.0))}',
                "# HELP new_task_cancellation_rate Cancellation rate in terminal outcomes window.",
                "# TYPE new_task_cancellation_rate gauge",
                f'new_task_cancellation_rate {float(rates.get("cancellation_rate", 0.0))}',
            ]
        )

        alerts = metrics.get("alerts", {})
        lines.extend(
            [
                "# HELP new_task_alert_evaluated Whether alert thresholds were evaluated.",
                "# TYPE new_task_alert_evaluated gauge",
                f'new_task_alert_evaluated {1 if bool(alerts.get("evaluated")) else 0}',
                "# HELP new_task_alert_triggered Whether any alert threshold was triggered.",
                "# TYPE new_task_alert_triggered gauge",
                f'new_task_alert_triggered {1 if bool(alerts.get("triggered")) else 0}',
                "# HELP new_task_alert_terminal_total Terminal task sample size used for alert evaluation.",
                "# TYPE new_task_alert_terminal_total gauge",
                f'new_task_alert_terminal_total {int(alerts.get("terminal_total", 0))}',
            ]
        )

        reasons = alerts.get("reasons", [])
        lines.extend(
            [
                "# HELP new_task_alert_reason Indicates which alert reasons are currently active.",
                "# TYPE new_task_alert_reason gauge",
            ]
        )
        if isinstance(reasons, list):
            for reason in sorted(str(item) for item in reasons):
                lines.append(f'new_task_alert_reason{{reason="{self._prometheus_escape(reason)}"}} 1')

        return "\n".join(lines) + "\n"

    @staticmethod
    def _prometheus_escape(value: str) -> str:
        escaped = value.replace("\\", "\\\\")
        escaped = escaped.replace("\n", "\\n")
        return escaped.replace('"', '\\"')

    def _work_loop(self) -> None:
        while not self._stop_event.is_set():
            task_id = self._queue.dequeue(timeout_seconds=1)
            if not task_id:
                continue

            if self._executor is not None:
                self._executor.submit(self._process_task, task_id)
            else:
                self._process_task(task_id)

    def _process_task(self, task_id: str) -> None:
        if not self._store.mark_running(task_id):
            record = self._store.get_task(task_id)
            if record is not None and record.status == "pending":
                delay = 0
                run_at_epoch: float | None = None
                if record.run_at is not None:
                    run_at_epoch = self._iso_to_epoch(record.run_at)
                    delay = self._delay_seconds(record.run_at)
                if record.next_retry_at is not None:
                    run_at_epoch = self._iso_to_epoch(record.next_retry_at)
                    delay = max(delay, self._delay_seconds(record.next_retry_at))
                self._queue.enqueue(
                    task_id,
                    delay_seconds=delay,
                    priority=record.priority,
                    run_at_epoch=run_at_epoch,
                )
            return

        record = self._store.get_task(task_id)
        if record is None:
            return
        self._events.append_event(
            task_id,
            "task.started",
            {"retry_count": record.retry_count, "priority": record.priority},
        )
        task_name = str(record.payload.get("task") or "anonymous")
        self._events.append_event(
            task_id,
            "task.dispatching",
            {
                "task": task_name,
                "retry_count": record.retry_count,
                "priority": record.priority,
            },
        )

        payload_for_run = dict(record.payload)
        raw_targets = payload_for_run.pop("_dispatch_targets", None)
        dispatch_targets: list[dict[str, int]] = []
        if isinstance(raw_targets, list):
            for item in raw_targets:
                if not isinstance(item, dict):
                    continue
                device_id_raw = item.get("device_id")
                cloud_id_raw = item.get("cloud_id", 1)
                if device_id_raw is None or cloud_id_raw is None:
                    continue
                try:
                    device_id = int(str(device_id_raw))
                    cloud_id = int(str(cloud_id_raw))
                except Exception:
                    continue
                if device_id < 1 or cloud_id < 1:
                    continue
                dispatch_targets.append({"device_id": device_id, "cloud_id": cloud_id})
        if not dispatch_targets:
            if record.devices:
                dispatch_targets = [{"device_id": int(device_id), "cloud_id": 1} for device_id in record.devices]
            else:
                dispatch_targets = [{"device_id": 1, "cloud_id": 1}]

        try:
            target_results: list[dict[str, Any]] = []
            first_failure: dict[str, Any] | None = None

            should_resolve_target = (os.getenv("MYT_ENABLE_RPC", "1") != "0") and self._plugin_loader.has(task_name)

            for target in dispatch_targets:
                target_runtime: dict[str, Any] | None = None
                target_error: dict[str, Any] | None = None
                if should_resolve_target:
                    target_runtime, target_error = self._resolve_target_runtime(
                        target,
                        enforce_availability=True,
                    )
                if target_error is not None:
                    target_result = {
                        "target": target,
                        "result": target_error,
                    }
                    target_results.append(target_result)
                    if first_failure is None:
                        first_failure = target_error
                    continue

                target_payload = dict(payload_for_run)
                target_payload["_task_id"] = task_id
                target_payload["_cloud_target"] = f"Unit #{target.get('device_id')}-{target.get('cloud_id')}"

                if target_runtime is not None:
                    target_payload["_target"] = target_runtime

                result = self._runner.run(
                    target_payload,
                    should_cancel=lambda task_id=task_id: self._store.is_cancel_requested(task_id),
                )
                target_result = {                    "target": target_runtime or target,
                    "result": result,
                }
                target_results.append(target_result)
                if not bool(result.get("ok")) and first_failure is None:
                    first_failure = result

            if first_failure is None:
                result = {
                    "ok": True,
                    "task": task_name,
                    "status": "completed",
                    "target_count": len(target_results),
                    "targets": target_results,
                }
            else:
                result = {
                    "ok": False,
                    "task": task_name,
                    "status": str(first_failure.get("status") or "failed"),
                    "message": str(first_failure.get("message") or "task failed"),
                    "target_count": len(target_results),
                    "targets": target_results,
                }

            self._events.append_event(
                task_id,
                "task.dispatch_result",
                {
                    "task": str(result.get("task") or task_name),
                    "status": str(result.get("status") or "unknown"),
                    "ok": bool(result.get("ok")),
                    "checkpoint": str(result.get("checkpoint") or ""),
                },
            )
            if self._store.is_cancel_requested(task_id) or str(result.get("status")) == "cancelled":
                self._store.mark_cancelled(task_id, message="cancelled by user")
                self._events.append_event(task_id, "task.cancelled", self._metrics_payload(task_id, {"reason": "user"}))
                return

            if bool(result.get("ok")):
                self._store.mark_completed(task_id, result=result)
                self._events.append_event(task_id, "task.completed", self._metrics_payload(task_id, {"ok": True}))
            else:
                error = str(result.get("message", "task failed"))
                self._account_feedback.handle_terminal_failure(record.payload, error)
                retry_record = self._store.schedule_retry(task_id, error=error)
                if retry_record is not None and retry_record.next_retry_at is not None:
                    self._queue.enqueue(
                        task_id,
                        delay_seconds=self._delay_seconds(retry_record.next_retry_at),
                        priority=retry_record.priority,
                        run_at_epoch=self._iso_to_epoch(retry_record.next_retry_at),
                    )
                    self._events.append_event(
                        task_id,
                        "task.retry_scheduled",
                        {
                            "retry_count": retry_record.retry_count,
                            "max_retries": retry_record.max_retries,
                            "next_retry_at": retry_record.next_retry_at,
                            "error": error,
                        },
                    )
                else:
                    if self._store.is_cancel_requested(task_id):
                        self._store.mark_cancelled(task_id, message="cancelled by user")
                        self._events.append_event(
                            task_id,
                            "task.cancelled",
                            self._metrics_payload(task_id, {"reason": "user_exception_path"}),
                        )
                        return
                    self._store.mark_failed(task_id, error=error, result=result)
                    self._events.append_event(
                        task_id,
                        "task.failed",
                        self._metrics_payload(task_id, {"error": error}),
                    )
        except Exception as exc:
            error = str(exc)
            retry_record = self._store.schedule_retry(task_id, error=error)
            if retry_record is not None and retry_record.next_retry_at is not None:
                self._queue.enqueue(
                    task_id,
                    delay_seconds=self._delay_seconds(retry_record.next_retry_at),
                    priority=retry_record.priority,
                    run_at_epoch=self._iso_to_epoch(retry_record.next_retry_at),
                )
                self._events.append_event(
                    task_id,
                    "task.retry_scheduled",
                    {
                        "retry_count": retry_record.retry_count,
                        "max_retries": retry_record.max_retries,
                        "next_retry_at": retry_record.next_retry_at,
                        "error": error,
                    },
                )
            else:
                if self._store.is_cancel_requested(task_id):
                    self._store.mark_cancelled(task_id, message="cancelled by user")
                    self._events.append_event(
                        task_id,
                        "task.cancelled",
                        self._metrics_payload(task_id, {"reason": "user_exception_path"}),
                    )
                    return
                self._store.mark_failed(task_id, error=error)
                self._events.append_event(
                    task_id,
                    "task.failed",
                    self._metrics_payload(task_id, {"error": error}),
                )
        time.sleep(0)


    def _resolve_target_runtime(
        self,
        target: dict[str, int],
        enforce_availability: bool,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        try:
            device_id_raw = target.get("device_id")
            cloud_id_raw = target.get("cloud_id")
            if device_id_raw is None or cloud_id_raw is None:
                raise ValueError("missing target keys")
            device_id = int(device_id_raw)
            cloud_id = int(cloud_id_raw)
        except Exception:
            device_id = 0
            cloud_id = 0
        if device_id < 1 or cloud_id < 1:
            return None, {
                "ok": False,
                "status": "failed_target_validation",
                "code": "invalid_target",
                "message": f"invalid target: device_id={device_id}, cloud_id={cloud_id}",
            }

        try:
            info = self._device_manager.get_device_info(device_id)
        except Exception as exc:
            return None, {
                "ok": False,
                "status": "failed_target_validation",
                "code": "target_not_found",
                "message": str(exc),
            }

        clouds_raw = info.get("cloud_machines") if isinstance(info, dict) else []
        clouds = clouds_raw if isinstance(clouds_raw, list) else []
        cloud = None
        for item in clouds:
            if not isinstance(item, dict):
                continue
            cloud_value = item.get("cloud_id", 0)
            try:
                cloud_value_int = int(cloud_value)
            except Exception:
                cloud_value_int = 0
            if cloud_value_int == cloud_id:
                cloud = item
                break
        if cloud is None:
            return None, {
                "ok": False,
                "status": "failed_target_validation",
                "code": "cloud_not_found",
                "message": f"cloud_id out of range for device {device_id}: {cloud_id}",
            }

        availability_state = str(cloud.get("availability_state") or "unknown")
        if enforce_availability and availability_state != "available":
            return None, {
                "ok": False,
                "status": "failed_target_unavailable",
                "code": "target_unavailable",
                "message": (
                    f"target unavailable: device={device_id}, cloud={cloud_id}, "
                    f"state={availability_state}"
                ),
            }

        return {
            "device_id": device_id,
            "cloud_id": cloud_id,
            "device_ip": str(info.get("ip") or ""),
            "api_port": int(cloud.get("api_port", 0)),
            "rpa_port": int(cloud.get("rpa_port", 0)),
            "availability_state": availability_state,
        }, None

    def _delay_seconds(self, next_retry_at: str) -> int:
        dt = datetime.fromisoformat(next_retry_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (dt - now).total_seconds()
        if delta <= 0:
            return 0
        return int(math.ceil(delta))

    def _iso_to_epoch(self, timestamp: str) -> float:
        dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()

    def _metrics_payload(self, task_id: str, extra: dict[str, Any]) -> dict[str, Any]:
        record = self._store.get_task(task_id)
        if record is None:
            return extra
        started_at = record.started_at
        finished_at = record.finished_at
        duration_ms = None
        if started_at and finished_at:
            try:
                duration_ms = int((datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds() * 1000)
            except Exception:
                duration_ms = None
        payload = {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "retry_count": record.retry_count,
        }
        payload.update(extra)
        return payload

    def _recover_stale_running_tasks(self) -> None:
        stale_after_seconds = self._stale_running_seconds()
        stale_before = (datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)).isoformat()
        recovered = self._store.recover_stale_running_tasks(stale_before=stale_before)
        for record in recovered:
            delay = 0
            run_at_epoch: float | None = None
            if record.run_at is not None:
                run_at_epoch = self._iso_to_epoch(record.run_at)
                delay = self._delay_seconds(record.run_at)
            if record.next_retry_at is not None:
                run_at_epoch = self._iso_to_epoch(record.next_retry_at)
                delay = max(delay, self._delay_seconds(record.next_retry_at))
            self._queue.enqueue(
                record.task_id,
                delay_seconds=delay,
                priority=record.priority,
                run_at_epoch=run_at_epoch,
            )
            self._events.append_event(
                record.task_id,
                "task.recovered_stale_running",
                {
                    "stale_after_seconds": stale_after_seconds,
                    "previous_status": "running",
                },
            )

    @staticmethod
    def _stale_running_seconds() -> int:
        raw = os.environ.get("MYT_TASK_STALE_RUNNING_SECONDS", "300").strip()
        try:
            parsed = int(raw)
        except ValueError:
            return 300
        return max(0, parsed)


_controller: TaskController | None = None
_controller_lock = threading.Lock()


def get_task_controller() -> TaskController:
    global _controller
    with _controller_lock:
        if _controller is None:
            _controller = TaskController()
        return _controller


def reset_task_controller_for_tests() -> None:
    global _controller
    with _controller_lock:
        if _controller is not None:
            _controller.stop()
        _controller = None


def override_task_controller_for_tests(controller: TaskController) -> None:
    global _controller
    with _controller_lock:
        if _controller is not None:
            _controller.stop()
        _controller = controller
