const $ = (id) => document.getElementById(id);

const apiStatus = $("apiStatus");
const devicesList = $("devicesList");
const hostIp = $("hostIp");
const totalDevices = $("totalDevices");
const deviceIps = $("deviceIps");
const configMsg = $("configMsg");
const runtimePayload = $("runtimePayload");
const runtimeResult = $("runtimeResult");
const logBox = $("logBox");

function setApiStatus(ok) {
  apiStatus.className = `badge ${ok ? "badge-ok" : "badge-warn"}`;
  apiStatus.textContent = ok ? "API: Online" : "API: Offline";
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
    devicesList.innerHTML = '<div class="device-item"><strong>No devices</strong></div>';
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
      <div class="device-meta">SDK: ${d.sdk_port}</div>
      <div class="device-meta">Clouds: ${clouds.length}</div>
      <div class="device-meta">Cloud-1 API/RPA: ${firstCloud ? `${firstCloud.api_port}/${firstCloud.rpa_port}` : "n/a"}</div>
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
    configMsg.textContent = "Load config failed";
    return;
  }
  hostIp.value = r.data.host_ip || "";
  totalDevices.value = r.data.total_devices || 1;
  deviceIps.value = JSON.stringify(r.data.device_ips || {}, null, 2);
  configMsg.textContent = "Config loaded";
}

async function saveConfig() {
  let parsedDeviceIps = {};
  try {
    parsedDeviceIps = JSON.parse(deviceIps.value || "{}");
  } catch (_) {
    configMsg.textContent = "device_ips JSON invalid";
    return;
  }

  const body = {
    host_ip: hostIp.value.trim(),
    total_devices: Number(totalDevices.value || 1),
    device_ips: parsedDeviceIps,
  };

  const r = await fetchJson("/api/config/", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  configMsg.textContent = r.ok ? "Config saved" : `Save failed (${r.status})`;
  if (r.ok) {
    await loadDevices();
  }
}

async function executeRuntime() {
  let payload = {};
  try {
    payload = JSON.parse(runtimePayload.value || "{}");
  } catch (_) {
    runtimeResult.textContent = "Invalid JSON payload";
    return;
  }
  const r = await fetchJson("/api/runtime/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  runtimeResult.textContent = JSON.stringify(r.data, null, 2);
}

function connectLogs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/logs`);

  ws.onopen = () => {
    logBox.textContent += "[ws] connected\n";
    ws.send(JSON.stringify({ type: "ping" }));
  };
  ws.onmessage = (e) => {
    logBox.textContent += `${e.data}\n`;
    logBox.scrollTop = logBox.scrollHeight;
  };
  ws.onclose = () => {
    logBox.textContent += "[ws] closed, reconnecting...\n";
    setTimeout(connectLogs, 1500);
  };
}

$("refreshAll").addEventListener("click", async () => {
  await Promise.all([loadHealth(), loadDevices(), loadConfig()]);
});
$("refreshDevices").addEventListener("click", loadDevices);
$("saveConfig").addEventListener("click", saveConfig);
$("runTask").addEventListener("click", executeRuntime);
$("clearLogs").addEventListener("click", () => {
  logBox.textContent = "";
});

(async function init() {
  await Promise.all([loadHealth(), loadDevices(), loadConfig()]);
  connectLogs();
})();
