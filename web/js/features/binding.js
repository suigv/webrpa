/**
 * Binding Master - AI-Assisted UI Feature Distillation
 */

let bindingRecords = [];
let currentCapture = null;
let currentApp = 'unknown';

export function initBindingMaster() {
    const modal = document.getElementById('bindingMasterModal');
    const openBtn = document.getElementById('openBindingMaster');
    const closeBtn = document.getElementById('closeBindingMaster');

    if (openBtn) {
        openBtn.addEventListener('click', () => {
            modal.style.display = 'flex';
            resetBindingMaster();
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });
    }

    // Capture current page
    document.getElementById('captureStateBtn').addEventListener('click', captureCurrentState);

    // Generate code
    document.getElementById('generateBindingCodeBtn').addEventListener('click', generateBindingCode);

    // Add feature manually
    document.getElementById('addBindFeature').addEventListener('click', () => {
        const input = document.getElementById('newBindFeature');
        const val = input.value.trim();
        if (val && currentCapture) {
            currentCapture.analysis.features.push(val);
            input.value = '';
            renderBindingDetail(currentCapture);
        }
    });

    // Copy code
    document.getElementById('copyBindingCode').addEventListener('click', () => {
        const code = document.getElementById('bindingCodeTerminal').value;
        navigator.clipboard.writeText(code);
        alert('代码已复制到剪贴板');
    });
}

function resetBindingMaster() {
    bindingRecords = [];
    currentCapture = null;
    const list = document.getElementById('bindingStateList');
    if (list) {
        list.replaceChildren();
        const empty = document.createElement('div');
        empty.className = 'p-8 text-center text-muted text-xs';
        empty.textContent = '暂无记录，请点击“采集”';
        list.appendChild(empty);
    }
    showBindingView('empty');
}

async function captureCurrentState() {
    const btn = document.getElementById('captureStateBtn');
    const originalText = btn.innerText;
    btn.innerText = '分析中...';
    btn.disabled = true;

    // Use current unit info from global scope or specific DOM
    const deviceId = parseInt(document.body.dataset.currentDeviceId);
    const cloudId = parseInt(document.body.dataset.currentCloudId) || 1;
    
    // Attempt to guess app name from recent logs or user input? 
    // For now, prompt if unknown
    if (currentApp === 'unknown') {
        const guess = prompt("请输入正在分析的 App 名称 (例如: tiktok, facebook):", "app");
        if (!guess) {
            btn.innerText = originalText;
            btn.disabled = false;
            return;
        }
        currentApp = guess;
    }

    try {
        const res = await fetch('/api/binding/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_id: deviceId,
                cloud_id: cloudId,
                app_name: currentApp,
                known_states: bindingRecords.map(r => r.state_id)
            })
        });

        const data = await res.json();
        if (data.ok) {
            currentCapture = {
                state_id: data.analysis.state_id,
                analysis: data.analysis,
                xml: data.xml,
                timestamp: new Date().toLocaleTimeString()
            };
            
            // Add to records if unique-ish
            bindingRecords.push(currentCapture);
            renderBindingList();
            renderBindingDetail(currentCapture);
        } else {
            const msg = typeof data.detail === 'object' ? JSON.stringify(data.detail) : data.detail;
            alert("采集失败: " + msg);
        }
    } catch (e) {
        alert("网络错误: " + e.message);
    } finally {
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

function renderBindingList() {
    const list = document.getElementById('bindingStateList');
    list.replaceChildren();
    bindingRecords.forEach((rec, idx) => {
        const div = document.createElement('div');
        div.className = 'list-item p-3 cursor-pointer hover:bg-bg-active flex justify-between items-center';

        const left = document.createElement('div');
        left.className = 'flex-1';
        const title = document.createElement('div');
        title.className = 'font-bold text-sm text-primary';
        title.textContent = String(rec.state_id || '');
        const ts = document.createElement('div');
        ts.className = 'text-[10px] text-muted';
        ts.textContent = String(rec.timestamp || '');
        left.append(title, ts);

        const removeBtn = document.createElement('button');
        removeBtn.className = 'btn btn-text btn-xs text-error';
        removeBtn.textContent = '×';
        removeBtn.onclick = (e) => {
            e.stopPropagation();
            bindingRecords.splice(idx, 1);
            renderBindingList();
            showBindingView('empty');
        };

        div.append(left, removeBtn);
        div.onclick = () => renderBindingDetail(rec);
        list.appendChild(div);
    });
}

function renderBindingDetail(rec) {
    currentCapture = rec;
    showBindingView('detail');
    
    const idInput = document.getElementById('bindStateId');
    idInput.value = rec.state_id;
    idInput.onchange = (e) => { rec.state_id = e.target.value; renderBindingList(); };
    
    const featList = document.getElementById('bindFeaturesList');
    featList.replaceChildren();
    rec.analysis.features.forEach((feat, fidx) => {
        const fdiv = document.createElement('div');
        fdiv.className = 'flex items-center gap-2 bg-bg-sidebar p-2 rounded text-xs';

        const featSpan = document.createElement('span');
        featSpan.className = 'flex-1 font-mono';
        featSpan.textContent = String(feat ?? '');

        const removeBtn = document.createElement('button');
        removeBtn.className = 'text-error';
        removeBtn.textContent = '×';
        removeBtn.onclick = () => {
            rec.analysis.features.splice(fidx, 1);
            renderBindingDetail(rec);
        };

        fdiv.append(featSpan, removeBtn);
        featList.appendChild(fdiv);
    });
    
    document.getElementById('bindXmlPreview').innerText = rec.xml.substring(0, 2000) + (rec.xml.length > 2000 ? '...' : '');
}

async function generateBindingCode() {
    if (bindingRecords.length === 0) return alert("请先采集至少一个状态");
    
    const btn = document.getElementById('generateBindingCodeBtn');
    btn.disabled = true;
    btn.innerText = '生成中...';

    try {
        const res = await fetch('/api/binding/draft', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                app_name: currentApp,
                records: bindingRecords.map(r => ({
                    state_id: r.state_id,
                    features: r.analysis.features
                }))
            })
        });

        const data = await res.json();
        if (data.ok) {
            showBindingView('code');
            document.getElementById('bindingCodeTerminal').value = data.code;
        } else {
            const msg = typeof data.detail === 'object' ? JSON.stringify(data.detail) : data.detail;
            alert("生成失败: " + msg);
        }
    } catch (e) {
        alert("网络错误: " + e.message);
    } finally {
        btn.disabled = false;
        btn.innerText = '生成 Python 代码';
    }
}

function showBindingView(view) {
    document.getElementById('bindingEmptyView').style.display = view === 'empty' ? 'flex' : 'none';
    document.getElementById('bindingDetailView').style.display = view === 'detail' ? 'flex' : 'none';
    document.getElementById('bindingCodeView').style.display = view === 'code' ? 'flex' : 'none';
}
