const $ = (id) => document.getElementById(id);

const apiStatus = $("apiStatus");
const devicesList = $("devicesList");
const hostIp = $("hostIp");
const totalDevices = $("totalDevices");
const deviceIps = $("deviceIps");
const humanizedConfig = $("humanizedConfig");
const hzEnabled = $("hzEnabled");
const hzTypoProbability = $("hzTypoProbability");
const hzTypingDelayMin = $("hzTypingDelayMin");
const hzTypingDelayMax = $("hzTypingDelayMax");
const hzTypoDelayMin = $("hzTypoDelayMin");
const hzTypoDelayMax = $("hzTypoDelayMax");
const hzBackspaceDelayMin = $("hzBackspaceDelayMin");
const hzBackspaceDelayMax = $("hzBackspaceDelayMax");
const hzClickOffsetXMin = $("hzClickOffsetXMin");
const hzClickOffsetXMax = $("hzClickOffsetXMax");
const hzClickOffsetYMin = $("hzClickOffsetYMin");
const hzClickOffsetYMax = $("hzClickOffsetYMax");
const hzMoveDurationMin = $("hzMoveDurationMin");
const hzMoveDurationMax = $("hzMoveDurationMax");
const hzMoveStepsMin = $("hzMoveStepsMin");
const hzMoveStepsMax = $("hzMoveStepsMax");
const hzRandomSeed = $("hzRandomSeed");
const configMsg = $("configMsg");
const runtimePayload = $("runtimePayload");
const runtimeResult = $("runtimeResult");
const logBox = $("logBox");

const taskPriority = $("taskPriority");
const taskRunAt = $("taskRunAt");
const taskMaxRetries = $("taskMaxRetries");
const taskBackoff = $("taskBackoff");
const taskPayload = $("taskPayload");
const taskMsg = $("taskMsg");
const tasksList = $("tasksList");
const taskDetail = $("taskDetail");
const accountsInput = $("accountsInput");
const accountsMsg = $("accountsMsg");
const accountsPreview = $("accountsPreview");

let taskEventSource = null;

function setHumanizedForm(cfg) {
  const data = cfg || {};
  hzEnabled.checked = Boolean(data.enabled);
  hzTypoProbability.value = Number(data.typo_probability ?? 0.03);
  hzTypingDelayMin.value = Number(data.typing_delay_min ?? 0.04);
  hzTypingDelayMax.value = Number(data.typing_delay_max ?? 0.18);
  hzTypoDelayMin.value = Number(data.typo_delay_min ?? 0.04);
  hzTypoDelayMax.value = Number(data.typo_delay_max ?? 0.12);
  hzBackspaceDelayMin.value = Number(data.backspace_delay_min ?? 0.02);
  hzBackspaceDelayMax.value = Number(data.backspace_delay_max ?? 0.08);
  hzClickOffsetXMin.value = Number(data.click_offset_x_min ?? -4);
  hzClickOffsetXMax.value = Number(data.click_offset_x_max ?? 4);
  hzClickOffsetYMin.value = Number(data.click_offset_y_min ?? -4);
  hzClickOffsetYMax.value = Number(data.click_offset_y_max ?? 4);
  hzMoveDurationMin.value = Number(data.move_duration_min ?? 0.2);
  hzMoveDurationMax.value = Number(data.move_duration_max ?? 0.7);
  hzMoveStepsMin.value = Number(data.move_steps_min ?? 8);
  hzMoveStepsMax.value = Number(data.move_steps_max ?? 24);
  hzRandomSeed.value = data.random_seed === null || data.random_seed === undefined ? "" : String(data.random_seed);
  humanizedConfig.value = JSON.stringify(buildHumanizedFromForm(), null, 2);
}

function buildHumanizedFromForm() {
  const seedText = (hzRandomSeed.value || "").trim();
  return {
    enabled: Boolean(hzEnabled.checked),
    typo_probability: Number(hzTypoProbability.value || 0),
    typing_delay_min: Number(hzTypingDelayMin.value || 0),
    typing_delay_max: Number(hzTypingDelayMax.value || 0),
    typo_delay_min: Number(hzTypoDelayMin.value || 0),
    typo_delay_max: Number(hzTypoDelayMax.value || 0),
    backspace_delay_min: Number(hzBackspaceDelayMin.value || 0),
    backspace_delay_max: Number(hzBackspaceDelayMax.value || 0),
    click_offset_x_min: Number(hzClickOffsetXMin.value || 0),
    click_offset_x_max: Number(hzClickOffsetXMax.value || 0),
    click_offset_y_min: Number(hzClickOffsetYMin.value || 0),
    click_offset_y_max: Number(hzClickOffsetYMax.value || 0),
    move_duration_min: Number(hzMoveDurationMin.value || 0),
    move_duration_max: Number(hzMoveDurationMax.value || 0),
    move_steps_min: Number(hzMoveStepsMin.value || 1),
    move_steps_max: Number(hzMoveStepsMax.value || 1),
    random_seed: seedText === "" ? null : Number(seedText),
  };
}

function validateHumanizedForm(cfg) {
  if (!(cfg.typo_probability >= 0 && cfg.typo_probability <= 1)) {
    return "拼写错误概率必须在 0 到 1 之间";
  }
  const pairs = [
    ["typing_delay", cfg.typing_delay_min, cfg.typing_delay_max],
    ["typo_delay", cfg.typo_delay_min, cfg.typo_delay_max],
    ["backspace_delay", cfg.backspace_delay_min, cfg.backspace_delay_max],
    ["click_offset_x", cfg.click_offset_x_min, cfg.click_offset_x_max],
    ["click_offset_y", cfg.click_offset_y_min, cfg.click_offset_y_max],
    ["move_duration", cfg.move_duration_min, cfg.move_duration_max],
    ["move_steps", cfg.move_steps_min, cfg.move_steps_max],
  ];
  for (const [name, minV, maxV] of pairs) {
    if (minV > maxV) {
      return `${name}: 最小值必须 <= 最大值`;
    }
  }
  return "";
}

function setApiStatus(ok) {
  apiStatus.className = `badge ${ok ? "badge-ok" : "badge-warn"}`;
  apiStatus.textContent = ok ? "API: 在线" : "API: 离线";
}

async function fetchJson(url, opts = {}) {
  const res = await fetch(url, opts);
  const txt = await res.text();
  let data = txt;
  try {
    data = txt ? JSON.parse(txt) : {};
  } catch (_) {}
  return { ok: res.ok, status: res.status, data };
}

async function loadHealth() {
  try {
    const r = await fetchJson("/health");
    setApiStatus(r.ok);
  } catch (_) {
    setApiStatus(false);
  }
}

function renderDevices(items) {
  devicesList.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    devicesList.innerHTML = '<div class="device-item"><strong>暂无设备</strong></div>';
    return;
  }

  items.forEach((d) => {
    const clouds = Array.isArray(d.cloud_machines) ? d.cloud_machines : [];
    const firstCloud = clouds[0] || null;
    const node = document.createElement("div");
    node.className = "device-item";
    node.innerHTML = `
      <strong>#${d.device_id} • ${d.status}</strong>
      <div class="device-meta">IP: ${d.ip}</div>
      <div class="device-meta">SDK: ${d.sdk_port} (${d.sdk_port_role || "device_control_api"})</div>
      <div class="device-meta">云端: ${clouds.length}</div>
      <div class="device-meta">云端-1 API: ${firstCloud ? `${firstCloud.api_port} (${firstCloud.api_port_role || "cloud_api"})` : "无"}</div>
      <div class="device-meta">云端-1 RPA: ${firstCloud ? `${firstCloud.rpa_port} (${firstCloud.rpa_port_role || "mytrpc_control"})` : "无"}</div>
      <div class="device-meta">AI: ${d.ai_type}</div>
    `;
    devicesList.appendChild(node);
  });
}

async function loadDevices() {
  const r = await fetchJson("/api/devices/");
  if (r.ok) {
    renderDevices(r.data);
  }
}

async function loadConfig() {
  const r = await fetchJson("/api/config/");
  if (!r.ok) {
    configMsg.textContent = "加载配置失败";
    return;
  }
  hostIp.value = r.data.host_ip || "";
  totalDevices.value = r.data.total_devices || 1;
  deviceIps.value = JSON.stringify(r.data.device_ips || {}, null, 2);
  setHumanizedForm(r.data.humanized || {});
  configMsg.textContent = "配置已加载";
}

async function saveConfig() {
  let parsedDeviceIps = {};
  let parsedHumanized = {};
  try {
    parsedDeviceIps = JSON.parse(deviceIps.value || "{}");
  } catch (_) {
    configMsg.textContent = "设备 IP JSON 格式无效";
    return;
  }
  parsedHumanized = buildHumanizedFromForm();
  humanizedConfig.value = JSON.stringify(parsedHumanized, null, 2);
  const humanizedError = validateHumanizedForm(parsedHumanized);
  if (humanizedError) {
    configMsg.textContent = humanizedError;
    return;
  }

  const body = {
    host_ip: hostIp.value.trim(),
    total_devices: Number(totalDevices.value || 1),
    device_ips: parsedDeviceIps,
    humanized: parsedHumanized,
  };

  const r = await fetchJson("/api/config/", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  configMsg.textContent = r.ok ? "配置已保存" : `保存失败 (${r.status})`;
  if (r.ok) {
    await loadDevices();
  }
}

async function executeRuntime() {
  let payload = {};
  try {
    payload = JSON.parse(runtimePayload.value || "{}");
  } catch (_) {
    runtimeResult.textContent = "JSON 数据格式无效";
    return;
  }
  const r = await fetchJson("/api/runtime/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  runtimeResult.textContent = JSON.stringify(r.data, null, 2);
}

async function loadAccounts() {
  const [raw, parsed] = await Promise.all([
    fetchJson("/api/data/accounts"),
    fetchJson("/api/data/accounts/parsed"),
  ]);

  if (raw.ok) {
    accountsInput.value = raw.data.data || "";
  }

  if (parsed.ok) {
    const list = Array.isArray(parsed.data.accounts) ? parsed.data.accounts : [];
    accountsPreview.textContent = JSON.stringify(list, null, 2);
    accountsMsg.textContent = `已加载 ${list.length} 个账号`;
  } else {
    accountsMsg.textContent = "加载账号失败";
  }
}

async function importAccounts(overwrite) {
  const r = await fetchJson("/api/data/accounts/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content: accountsInput.value || "", overwrite }),
  });

  if (r.ok) {
    const d = r.data;
    accountsMsg.textContent = `成功导入 ${d.imported} (有效=${d.valid}, 无效=${d.invalid}), 已存储=${d.stored}`;
    await loadAccounts();
  } else {
    accountsMsg.textContent = `导入失败 (${r.status})`;
    accountsPreview.textContent = JSON.stringify(r.data, null, 2);
  }
}

function closeTaskEvents() {
  if (taskEventSource) {
    taskEventSource.close();
    taskEventSource = null;
  }
}

function openTaskEvents(taskId) {
  closeTaskEvents();
  taskEventSource = new EventSource(`/api/tasks/${taskId}/events`);
  taskEventSource.onmessage = () => {};
  taskEventSource.onerror = () => {
    closeTaskEvents();
  };
  ["task.created", "task.started", "task.retry_scheduled", "task.completed", "task.failed", "task.cancelled", "task.cancel_requested"].forEach((evt) => {
    taskEventSource.addEventListener(evt, async () => {
      await loadTaskDetail(taskId);
      await loadTasks();
    });
  });
}

function renderTasks(items) {
  tasksList.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    tasksList.innerHTML = '<div class="device-item"><strong>暂无任务</strong></div>';
    return;
  }
  items.forEach((t) => {
    const node = document.createElement("div");
    node.className = "device-item";
    node.innerHTML = `
      <strong>${t.task_id.slice(0, 8)} • ${t.status}</strong>
      <div class="device-meta">优先级: ${t.priority} | 运行时间: ${t.run_at || "立即"}</div>
      <div class="device-meta">重试: ${t.retry_count}/${t.max_retries} | 退避: ${t.retry_backoff_seconds}s</div>
      <div class="device-meta">创建时间: ${t.created_at}</div>
      <div style="margin-top:6px;display:flex;gap:6px;">
        <button class="btn btn-ghost" data-task-detail="${t.task_id}">详情</button>
        <button class="btn btn-ghost" data-task-cancel="${t.task_id}">取消</button>
        <button class="btn btn-ghost" data-task-watch="${t.task_id}">监听</button>
      </div>
    `;
    tasksList.appendChild(node);
  });

  tasksList.querySelectorAll("[data-task-detail]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const taskId = btn.getAttribute("data-task-detail");
      await loadTaskDetail(taskId);
    });
  });
  tasksList.querySelectorAll("[data-task-cancel]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const taskId = btn.getAttribute("data-task-cancel");
      await cancelTask(taskId);
    });
  });
  tasksList.querySelectorAll("[data-task-watch]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const taskId = btn.getAttribute("data-task-watch");
      openTaskEvents(taskId);
    });
  });
}

async function loadTasks() {
  const r = await fetchJson("/api/tasks/?limit=50");
  if (r.ok) {
    renderTasks(r.data);
  }
}

async function loadTaskDetail(taskId) {
  const r = await fetchJson(`/api/tasks/${taskId}`);
  if (r.ok) {
    taskDetail.textContent = JSON.stringify(r.data, null, 2);
  } else {
    taskDetail.textContent = JSON.stringify(r.data, null, 2);
  }
}

async function submitTask() {
  let script = {};
  try {
    script = JSON.parse(taskPayload.value || "{}");
  } catch (_) {
    taskMsg.textContent = "任务数据 JSON 格式无效";
    return;
  }
  const runAt = taskRunAt.value.trim();
  const body = {
    script,
    devices: [1],
    ai_type: "volc",
    max_retries: Number(taskMaxRetries.value || 0),
    retry_backoff_seconds: Number(taskBackoff.value || 2),
    priority: Number(taskPriority.value || 50),
    run_at: runAt || null,
  };
  const r = await fetchJson("/api/tasks/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (r.ok) {
    taskMsg.textContent = `任务已提交: ${r.data.task_id}`;
    await loadTasks();
    await loadTaskDetail(r.data.task_id);
    openTaskEvents(r.data.task_id);
  } else {
    taskMsg.textContent = `提交失败 (${r.status})`;
    taskDetail.textContent = JSON.stringify(r.data, null, 2);
  }
}

async function cancelTask(taskId) {
  const r = await fetchJson(`/api/tasks/${taskId}/cancel`, { method: "POST" });
  if (r.ok) {
    taskMsg.textContent = `已请求取消: ${taskId}`;
    await loadTasks();
    await loadTaskDetail(taskId);
  } else {
    taskMsg.textContent = `取消失败 (${r.status})`;
  }
}

function connectLogs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/logs`);

  ws.onopen = () => {
    logBox.textContent += "[ws] 已连接\n";
    ws.send(JSON.stringify({ type: "ping" }));
  };
  ws.onmessage = (e) => {
    logBox.textContent += `${e.data}\n`;
    logBox.scrollTop = logBox.scrollHeight;
  };
  ws.onclose = () => {
    logBox.textContent += "[ws] 已断开，正在重连...\n";
    setTimeout(connectLogs, 1500);
  };
}

$("refreshAll").addEventListener("click", async () => {
  await Promise.all([loadHealth(), loadDevices(), loadConfig(), loadTasks(), loadAccounts()]);
});
$("refreshDevices").addEventListener("click", loadDevices);
$("saveConfig").addEventListener("click", saveConfig);
$("runTask").addEventListener("click", executeRuntime);
$("refreshTasks").addEventListener("click", loadTasks);
$("submitTask").addEventListener("click", submitTask);
$("loadAccounts").addEventListener("click", loadAccounts);
$("importAccountsOverwrite").addEventListener("click", async () => {
  await importAccounts(true);
});
$("importAccountsAppend").addEventListener("click", async () => {
  await importAccounts(false);
});
$("clearLogs").addEventListener("click", () => {
  logBox.textContent = "";
});

(async function init() {
  await Promise.all([loadHealth(), loadDevices(), loadConfig(), loadTasks(), loadAccounts()]);
  connectLogs();
})();

// App Navigation Tab Switching
document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', (e) => {
    // Hide all active states
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(tab => tab.classList.remove('active'));
    
    // Set active state on clicked nav item and corresponding tab
    const currentBtn = e.currentTarget;
    currentBtn.classList.add('active');
    
    const targetId = currentBtn.getAttribute('data-tab');
    document.getElementById(targetId).classList.add('active');
  });
});