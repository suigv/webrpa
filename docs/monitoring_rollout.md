# Monitoring Rollout

## Scope

This repo does not ship a production Prometheus or Alertmanager deployment manifest.
The repo-backed baseline is:

1. One `webrpa` instance exposes `GET /api/tasks/metrics/prometheus`.
2. One external Prometheus server scrapes that endpoint.
3. The same Prometheus server loads the repo alert rules.
4. One external Alertmanager instance receives `NewTask*` alerts and forwards them to a webhook.

The rendered example for that baseline lives in `config/monitoring/rendered/single-node-example/`.

## Repo Ownership

- The repo owns the source templates in `config/monitoring/prometheus/` and `config/monitoring/alertmanager/`.
- The repo owns the render tool in `tools/render_task_metrics_monitoring.py`.
- The rendered files in `config/monitoring/rendered/single-node-example/` are a checked-in baseline example, generated from the tool.
- Operators own environment-specific deployment wiring outside this repo, including Prometheus main config, Alertmanager main config, network exposure, secrets, and the real webhook target.

Do not hand-edit the rendered example as an environment source of truth. Re-render from `tools/render_task_metrics_monitoring.py` when target values change.

## Baseline Values

The checked-in rendered example uses these baseline values:

- `webrpa` target: `127.0.0.1:8001`
- metrics path: `/api/tasks/metrics/prometheus`
- scrape interval: `30s`
- metrics window: `3600`
- failure rate threshold: `0.2`
- cancellation rate threshold: `0.2`
- minimum terminal samples: `20`
- Alertmanager receiver: `webrpa-task-alerts`
- Alertmanager webhook URL: `http://127.0.0.1:19093/webhook`

For a real deployment, replace at least these values before rollout:

- the scrape target host and port
- the Alertmanager webhook URL

You may also replace the receiver name, scrape interval, and threshold values if your environment needs different routing or alert sensitivity.

## Render Command

Generate the same baseline example with:

```bash
./.venv/bin/python tools/render_task_metrics_monitoring.py \
  --output-dir config/monitoring/rendered/single-node-example
```

Generate an environment-specific variant with explicit target and webhook values:

```bash
./.venv/bin/python tools/render_task_metrics_monitoring.py \
  --target webrpa.example.internal:8001 \
  --alertmanager-webhook-url https://alerts.example.com/webrpa \
  --output-dir config/monitoring/rendered/prod-example
```

## Files in the Baseline

- Scrape job: `config/monitoring/rendered/single-node-example/task_metrics_scrape.yml`
- Prometheus alert rules: `config/monitoring/rendered/single-node-example/task_metrics_alerts.yml`
- Alertmanager route and receiver: `config/monitoring/rendered/single-node-example/task_metrics_alertmanager.yml`

## Deployment Chain

### 1. Expose the `webrpa` metrics endpoint

Start `webrpa` in the usual RPC-disabled baseline and make sure the Prometheus endpoint is reachable from the external Prometheus host:

```bash
MYT_ENABLE_RPC=0 ./.venv/bin/python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Raw endpoint check:

```bash
curl "http://127.0.0.1:8001/api/tasks/metrics/prometheus"
```

That endpoint is the source of truth for the scrape job.

### 2. Load the scrape job into external Prometheus

Use `config/monitoring/rendered/single-node-example/task_metrics_scrape.yml` as the repo-backed scrape job content.

Your external Prometheus deployment still needs a main config that references a scrape job and Alertmanager target. A minimal baseline shape is:

```yaml
scrape_configs:
  - job_name: new-task-metrics
    scrape_interval: 30s
    metrics_path: /api/tasks/metrics/prometheus
    params:
      window_seconds: ['3600']
      failure_rate_threshold: ['0.2']
      cancellation_rate_threshold: ['0.2']
      min_terminal_samples: ['20']
    static_configs:
      - targets: ['127.0.0.1:8001']

rule_files:
  - /etc/prometheus/task_metrics_alerts.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

`webrpa` only provides the job content and rules content. The external Prometheus deployment owns how those files are mounted and how the Alertmanager host is addressed.

### 3. Load the alert rules into external Prometheus

Mount `config/monitoring/rendered/single-node-example/task_metrics_alerts.yml` into the Prometheus rules path referenced by `rule_files`.

This baseline includes:

- `NewTaskAlertThresholdTriggered`
- `NewTaskFailureRateHigh`
- `NewTaskCancellationRateHigh`
- `NewTaskStaleRunningRecovered`

The stale-running rule is informational. It fires when `task.recovered_stale_running` events appear in the exported task metrics.

### 4. Load the Alertmanager route

Use `config/monitoring/rendered/single-node-example/task_metrics_alertmanager.yml` as the repo-backed Alertmanager route baseline.

Its flow is:

1. root route defaults to `webrpa-task-alerts`
2. child route matches `alertname=~"NewTask.*"`
3. receiver posts to the configured webhook URL

The checked-in example points to `http://127.0.0.1:19093/webhook`. Replace that with the real webhook URL before rollout.

## End-to-End Verification

Use this repo-backed sequence to verify the chain without inventing a deployment shape that is not in the repo.

1. Verify the raw metrics endpoint:

   ```bash
   curl "http://127.0.0.1:8001/api/tasks/metrics/prometheus"
   ```

2. Verify the render command still produces the baseline assets:

   ```bash
   ./.venv/bin/python tools/render_task_metrics_monitoring.py \
     --output-dir config/monitoring/rendered/single-node-example
   ```

3. Verify the render tool contract with the focused test:

   ```bash
   ./.venv/bin/python -m pytest tests/test_task_metrics_monitoring_tool.py -q
   ```

4. In Prometheus, confirm:

   - target `new-task-metrics` is `UP`
   - `new_task_alert_triggered` and related task metrics appear in the expression browser
   - the rule group from `task_metrics_alerts.yml` is loaded

5. In Alertmanager, confirm:

   - the route config is loaded
   - `NewTask*` alerts appear under the expected receiver
   - the webhook endpoint receives the forwarded alert payload

## Operational Notes

- Keep the source templates untouched. Render new environment variants instead.
- Treat the checked-in `single-node-example` output as a documented baseline, not as a universal production manifest.
- If operators tune stale-running behavior with `MYT_TASK_STALE_RUNNING_SECONDS`, they should also review whether the alert thresholds and webhook policy still match the intended operational response.
