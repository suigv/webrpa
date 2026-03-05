import subprocess
import sys
from pathlib import Path


def _tool_path() -> Path:
    return Path(__file__).resolve().parents[1] / "tools" / "render_task_metrics_monitoring.py"


def test_render_task_metrics_monitoring_stdout_contains_scrape_and_rules():
    result = subprocess.run(
        [sys.executable, str(_tool_path())],
        check=True,
        capture_output=True,
        text=True,
    )
    output = result.stdout
    assert "job_name: new-task-metrics" in output
    assert "metrics_path: /api/tasks/metrics/prometheus" in output
    assert "window_seconds: ['3600']" in output
    assert "alert: NewTaskAlertThresholdTriggered" in output
    assert "alert: NewTaskStaleRunningRecovered" in output
    assert "receiver: webrpa-task-alerts" in output
    assert "url: http://127.0.0.1:19093/webhook" in output


def test_render_task_metrics_monitoring_writes_files_to_output_dir(tmp_path: Path):
    result = subprocess.run(
        [
            sys.executable,
            str(_tool_path()),
            "--target",
            "10.0.0.1:18001",
            "--window-seconds",
            "7200",
            "--failure-rate-threshold",
            "0.35",
            "--cancellation-rate-threshold",
            "0.4",
            "--min-terminal-samples",
            "50",
            "--alertmanager-receiver",
            "ops-task-alerts",
            "--alertmanager-webhook-url",
            "https://alerts.example.com/webrpa",
            "--output-dir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "wrote:" in result.stdout

    scrape = (tmp_path / "task_metrics_scrape.yml").read_text(encoding="utf-8")
    alerts = (tmp_path / "task_metrics_alerts.yml").read_text(encoding="utf-8")
    alertmanager = (tmp_path / "task_metrics_alertmanager.yml").read_text(encoding="utf-8")

    assert "targets: ['10.0.0.1:18001']" in scrape
    assert "window_seconds: ['7200']" in scrape
    assert "failure_rate_threshold: ['0.35']" in scrape
    assert "cancellation_rate_threshold: ['0.4']" in scrape
    assert "min_terminal_samples: ['50']" in scrape
    assert "alert: NewTaskFailureRateHigh" in alerts
    assert "alert: NewTaskStaleRunningRecovered" in alerts
    assert "receiver: ops-task-alerts" in alertmanager
    assert "url: https://alerts.example.com/webrpa" in alertmanager
