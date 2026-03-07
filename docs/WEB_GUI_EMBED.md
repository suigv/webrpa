# Web 前端嵌入桌面 GUI 指南

本项目支持将 Web 控制台作为桌面 GUI 使用：通过 webview 嵌入 `/web` 页面即可。

## 目标地址
- 默认建议与 README 保持一致：`http://127.0.0.1:8001/web`
- 若后端改用其他端口，桌面壳只需同步修改 URL

## 推荐流程
1. 启动后端服务。
2. 确认 `/health` 返回 200。
3. 打开桌面壳窗口（内嵌 webview）。
4. 在 webview 中加载 `/web` 地址。

当前 Web 控制台已公开的页面主要是：云机大厅、账号池、设置页，以及实时日志区域。

## 方案 A：pywebview（轻量）

```python
import threading
import webview
import uvicorn


def run_api():
    uvicorn.run("api.server:app", host="127.0.0.1", port=8001)


threading.Thread(target=run_api, daemon=True).start()
webview.create_window("MYT Console", "http://127.0.0.1:8001/web", width=1280, height=820)
webview.start()
```

## 方案 B：Flet / Flutter 壳
- 在后台进程启动 API。
- 创建带 webview 组件的桌面窗口。
- 将组件 URL 指向 `/web`。

## 方案 C：Electron 壳
- 后端仍使用 FastAPI。
- `BrowserWindow` 加载 `http://127.0.0.1:8001/web`。

## 稳定性建议
- 创建 webview 前，先确认健康检查接口返回 200。
- 前端需对日志 websocket（`/ws/logs`）做自动重连。
- API 与 webview 尽量同 host，减少 CORS 复杂度。
