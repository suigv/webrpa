from __future__ import annotations

import argparse
from pathlib import Path


def _fmt_float(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def build_scrape_config(
    *,
    target: str,
    metrics_path: str,
    scrape_interval: str,
    window_seconds: int,
    failure_rate_threshold: float,
    cancellation_rate_threshold: float,
    min_terminal_samples: int,
) -> str:
    failure_text = _fmt_float(failure_rate_threshold)
    cancellation_text = _fmt_float(cancellation_rate_threshold)
    return "\n".join(
        [
            "# Prometheus scrape config for webrpa task control-plane metrics",
            "scrape_configs:",
            "  - job_name: new-task-metrics",
            f"    scrape_interval: {scrape_interval}",
            f"    metrics_path: {metrics_path}",
            "    params:",
            f"      window_seconds: ['{window_seconds}']",
            f"      failure_rate_threshold: ['{failure_text}']",
            f"      cancellation_rate_threshold: ['{cancellation_text}']",
            f"      min_terminal_samples: ['{min_terminal_samples}']",
            "    static_configs:",
            f"      - targets: ['{target}']",
            "",
        ]
    )


def build_alert_rules() -> str:
    return "\n".join(
        [
            "# Prometheus alert rules for webrpa task control-plane metrics",
            "groups:",
            "  - name: new-task-control-plane",
            "    rules:",
            "      - alert: NewTaskAlertThresholdTriggered",
            "        expr: new_task_alert_triggered == 1",
            "        for: 2m",
            "        labels:",
            "          severity: warning",
            "        annotations:",
            "          summary: 'Task reliability threshold triggered'",
            "          description: 'Failure/cancellation ratio exceeded configured threshold in the task metrics window.'",
            "",
            "      - alert: NewTaskFailureRateHigh",
            "        expr: new_task_alert_reason{reason=\"failure_rate_exceeded\"} == 1",
            "        for: 2m",
            "        labels:",
            "          severity: warning",
            "        annotations:",
            "          summary: 'Task failure rate is high'",
            "          description: 'new_task_failure_rate exceeded configured threshold.'",
            "",
            "      - alert: NewTaskCancellationRateHigh",
            "        expr: new_task_alert_reason{reason=\"cancellation_rate_exceeded\"} == 1",
            "        for: 2m",
            "        labels:",
            "          severity: warning",
            "        annotations:",
            "          summary: 'Task cancellation rate is high'",
            "          description: 'new_task_cancellation_rate exceeded configured threshold.'",
            "",
            "      - alert: NewTaskStaleRunningRecovered",
            "        expr: new_task_event_type_count{event_type=\"task.recovered_stale_running\"} > 0",
            "        for: 0m",
            "        labels:",
            "          severity: info",
            "        annotations:",
            "          summary: 'Stale-running task recovery detected'",
            "          description: 'One or more stale running tasks were recovered and re-enqueued.'",
            "",
        ]
    )


def build_alertmanager_config(*, receiver_name: str, webhook_url: str) -> str:
    return "\n".join(
        [
            "# Alertmanager routing config for webrpa task metrics alerts",
            "route:",
            f"  receiver: {receiver_name}",
            "  group_by: ['alertname']",
            "  group_wait: 30s",
            "  group_interval: 5m",
            "  repeat_interval: 2h",
            "  routes:",
            f"    - receiver: {receiver_name}",
            "      matchers:",
            "        - alertname=~\"NewTask.*\"",
            "",
            "receivers:",
            f"  - name: {receiver_name}",
            "    webhook_configs:",
            f"      - url: {webhook_url}",
            "        send_resolved: true",
            "",
        ]
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render Prometheus scrape + alert config for task metrics")
    _ = parser.add_argument("--target", default="127.0.0.1:8001", help="Task API target host:port")
    _ = parser.add_argument("--metrics-path", default="/api/tasks/metrics/prometheus", help="Prometheus metrics path")
    _ = parser.add_argument("--scrape-interval", default="30s", help="Prometheus scrape interval")
    _ = parser.add_argument("--window-seconds", type=int, default=3600, help="Metrics rolling window size")
    _ = parser.add_argument("--failure-rate-threshold", type=float, default=0.2, help="Failure ratio threshold")
    _ = parser.add_argument("--cancellation-rate-threshold", type=float, default=0.2, help="Cancellation ratio threshold")
    _ = parser.add_argument("--min-terminal-samples", type=int, default=20, help="Minimum terminal samples to evaluate")
    _ = parser.add_argument("--alertmanager-receiver", default="webrpa-task-alerts", help="Alertmanager receiver name")
    _ = parser.add_argument("--alertmanager-webhook-url", default="http://127.0.0.1:19093/webhook", help="Alertmanager webhook receiver URL")
    _ = parser.add_argument(
        "--output-dir",
        default=None,
        help="If provided, write task_metrics_scrape.yml and task_metrics_alerts.yml to this directory",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    arg_map = vars(args)

    target_obj = arg_map["target"]
    metrics_path_obj = arg_map["metrics_path"]
    scrape_interval_obj = arg_map["scrape_interval"]
    window_seconds_obj = arg_map["window_seconds"]
    failure_rate_threshold_obj = arg_map["failure_rate_threshold"]
    cancellation_rate_threshold_obj = arg_map["cancellation_rate_threshold"]
    min_terminal_samples_obj = arg_map["min_terminal_samples"]
    alertmanager_receiver_obj = arg_map["alertmanager_receiver"]
    alertmanager_webhook_url_obj = arg_map["alertmanager_webhook_url"]
    output_dir_obj = arg_map.get("output_dir")

    if not isinstance(target_obj, str):
        raise TypeError("target must be a string")
    if not isinstance(metrics_path_obj, str):
        raise TypeError("metrics_path must be a string")
    if not isinstance(scrape_interval_obj, str):
        raise TypeError("scrape_interval must be a string")
    if not isinstance(window_seconds_obj, int):
        raise TypeError("window_seconds must be an int")
    if not isinstance(failure_rate_threshold_obj, float):
        raise TypeError("failure_rate_threshold must be a float")
    if not isinstance(cancellation_rate_threshold_obj, float):
        raise TypeError("cancellation_rate_threshold must be a float")
    if not isinstance(min_terminal_samples_obj, int):
        raise TypeError("min_terminal_samples must be an int")
    if not isinstance(alertmanager_receiver_obj, str):
        raise TypeError("alertmanager_receiver must be a string")
    if not isinstance(alertmanager_webhook_url_obj, str):
        raise TypeError("alertmanager_webhook_url must be a string")
    if output_dir_obj is not None and not isinstance(output_dir_obj, str):
        raise TypeError("output_dir must be a string when provided")

    target = target_obj
    metrics_path = metrics_path_obj
    scrape_interval = scrape_interval_obj
    window_seconds = window_seconds_obj
    failure_rate_threshold = failure_rate_threshold_obj
    cancellation_rate_threshold = cancellation_rate_threshold_obj
    min_terminal_samples = min_terminal_samples_obj
    alertmanager_receiver = alertmanager_receiver_obj
    alertmanager_webhook_url = alertmanager_webhook_url_obj
    output_dir = output_dir_obj

    scrape = build_scrape_config(
        target=target,
        metrics_path=metrics_path,
        scrape_interval=scrape_interval,
        window_seconds=window_seconds,
        failure_rate_threshold=failure_rate_threshold,
        cancellation_rate_threshold=cancellation_rate_threshold,
        min_terminal_samples=min_terminal_samples,
    )
    alerts = build_alert_rules()
    alertmanager = build_alertmanager_config(
        receiver_name=alertmanager_receiver,
        webhook_url=alertmanager_webhook_url,
    )

    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        scrape_path = output_path / "task_metrics_scrape.yml"
        alerts_path = output_path / "task_metrics_alerts.yml"
        alertmanager_path = output_path / "task_metrics_alertmanager.yml"
        _ = scrape_path.write_text(scrape, encoding="utf-8")
        _ = alerts_path.write_text(alerts, encoding="utf-8")
        _ = alertmanager_path.write_text(alertmanager, encoding="utf-8")
        print(f"wrote: {scrape_path}")
        print(f"wrote: {alerts_path}")
        print(f"wrote: {alertmanager_path}")
        return

    print(scrape)
    print("---")
    print(alerts)
    print("---")
    print(alertmanager)


if __name__ == "__main__":
    main()
