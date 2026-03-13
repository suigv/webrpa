# 监控体系部署指南 (Monitoring Rollout)

本指南介绍如何将 WebRPA 的实时指标集成到外部监控系统（如 Prometheus 和 Grafana）。

---

## 1. 监控架构概览

WebRPA 内部维护了一个任务执行指标服务 (`TaskMetricsService`)，并提供了两个主要的 HTTP 端点：

1.  **JSON API** (`/api/tasks/metrics`)：用于控制台前端展示实时状态。
2.  **Prometheus Exporter** (`/api/tasks/metrics/prometheus`)：用于监控系统抓取。

---

## 2. 部署 Prometheus 抓取任务

在你的 Prometheus 配置文件 (`prometheus.yml`) 中，添加如下抓取目标：

```yaml
scrape_configs:
  - job_name: 'webrpa-tasks'
    metrics_path: '/api/tasks/metrics/prometheus'
    # 可选：通过查询参数指定监控窗口（单位：秒）
    # 默认监控过去 3600 秒（1 小时）内的终端状态任务
    params:
      window_seconds: ['3600']
    static_configs:
      - targets: ['localhost:8001']
```

---

## 3. 指标说明 (Exported Metrics)

| 指标名称 | 类型 | 标签 | 说明 |
|---|---|---|---|
| `webrpa_task_terminal_total` | Counter | `status` | 已结束的任务总量（成功、失败、取消）。 |
| `webrpa_task_active_total` | Gauge | `status` | 当前活跃的任务量（待处理、运行中）。 |
| `webrpa_task_failure_rate` | Gauge | — | 指定窗口内的任务失败率（0.0 ~ 1.0）。 |
| `webrpa_task_duration_seconds_avg` | Gauge | — | 任务平均耗时。 |

---

## 4. 告警策略建议 (Alerting Rules)

建议在 Prometheus Alertmanager 中配置以下告警规则：

### 4.1 任务失败率过高
- **表达式**：`webrpa_task_failure_rate > 0.2`
- **说明**：当过去 1 小时内任务失败率超过 20% 时触发告警，通常预示着目标 UI 发生了重大变更或云机集群存在连接问题。

### 4.2 长时间运行的停滞任务
- **表达式**：`webrpa_task_active_total{status="running"} > 10` (持续 10 分钟以上)
- **说明**：如果大量任务卡在“运行中”状态且没有结束迹象，可能需要检查僵尸任务清理机制。

---

## 5. 渲染监控快照

系统在 `config/monitoring/rendered/` 目录下提供了一些 Grafana 面板的 JSON 模板。
- [ ] 导入 `dashboard_v1.json` 到你的 Grafana 实例。
- [ ] 确保数据源指向你的 Prometheus 服务器。
