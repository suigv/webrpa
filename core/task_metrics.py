from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from core.task_events import TaskEventStore
from core.task_store import TaskRecord, TaskStore


def build_task_metrics_payload(record: TaskRecord | None, extra: dict[str, Any]) -> dict[str, Any]:
    if record is None:
        return dict(extra)

    duration_ms = None
    if record.started_at and record.finished_at:
        try:
            started_at = datetime.fromisoformat(record.started_at)
            finished_at = datetime.fromisoformat(record.finished_at)
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        except Exception:
            duration_ms = None

    payload = {
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "duration_ms": duration_ms,
        "retry_count": record.retry_count,
    }
    payload.update(extra)
    return payload


class TaskMetricsService:
    def __init__(self, store: TaskStore, event_store: TaskEventStore) -> None:
        self._store = store
        self._events = event_store

    def task_metrics(
        self,
        window_seconds: int = 3600,
        failure_rate_threshold: float = 0.2,
        cancellation_rate_threshold: float = 0.2,
        min_terminal_samples: int = 20,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        since = now - timedelta(seconds=max(0, int(window_seconds)))
        since_iso = since.isoformat()
        event_counts = self._events.count_by_type(since=since_iso)
        status_counts = self._store.status_counts()
        terminal_outcomes = {
            "completed": int(event_counts.get("task.completed", 0)),
            "failed": int(event_counts.get("task.failed", 0)),
            "cancelled": int(event_counts.get("task.cancelled", 0)),
        }
        terminal_total = max(0, sum(int(value) for value in terminal_outcomes.values()))
        completion_rate = (
            float(terminal_outcomes["completed"]) / terminal_total if terminal_total > 0 else 0.0
        )
        failure_rate = (
            float(terminal_outcomes["failed"]) / terminal_total if terminal_total > 0 else 0.0
        )
        cancellation_rate = (
            float(terminal_outcomes["cancelled"]) / terminal_total if terminal_total > 0 else 0.0
        )

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
                f"new_task_completion_rate {float(rates.get('completion_rate', 0.0))}",
                "# HELP new_task_failure_rate Failure rate in terminal outcomes window.",
                "# TYPE new_task_failure_rate gauge",
                f"new_task_failure_rate {float(rates.get('failure_rate', 0.0))}",
                "# HELP new_task_cancellation_rate Cancellation rate in terminal outcomes window.",
                "# TYPE new_task_cancellation_rate gauge",
                f"new_task_cancellation_rate {float(rates.get('cancellation_rate', 0.0))}",
            ]
        )

        alerts = metrics.get("alerts", {})
        lines.extend(
            [
                "# HELP new_task_alert_evaluated Whether alert thresholds were evaluated.",
                "# TYPE new_task_alert_evaluated gauge",
                f"new_task_alert_evaluated {1 if bool(alerts.get('evaluated')) else 0}",
                "# HELP new_task_alert_triggered Whether any alert threshold was triggered.",
                "# TYPE new_task_alert_triggered gauge",
                f"new_task_alert_triggered {1 if bool(alerts.get('triggered')) else 0}",
                "# HELP new_task_alert_terminal_total Terminal task sample size used for alert evaluation.",
                "# TYPE new_task_alert_terminal_total gauge",
                f"new_task_alert_terminal_total {int(alerts.get('terminal_total', 0))}",
            ]
        )

        lines.extend(
            [
                "# HELP new_task_alert_reason Indicates which alert reasons are currently active.",
                "# TYPE new_task_alert_reason gauge",
            ]
        )
        reasons = alerts.get("reasons", [])
        if isinstance(reasons, list):
            for reason in sorted(str(item) for item in reasons):
                lines.append(
                    f'new_task_alert_reason{{reason="{self._prometheus_escape(reason)}"}} 1'
                )

        return "\n".join(lines) + "\n"

    @staticmethod
    def _prometheus_escape(value: str) -> str:
        escaped = value.replace("\\", "\\\\")
        escaped = escaped.replace("\n", "\\n")
        return escaped.replace('"', '\\"')
