// 全局前端诊断脚本 (Non-Module)
console.log("Diag script active.");

window.onerror = function(msg, url, line, col, error) {
    var errorMsg = "捕获到致命错误:\n" + msg + "\n位置: " + url + ":" + line + ":" + col;
    if (error && error.stack) {
        errorMsg += "\n堆栈: " + error.stack;
    }
    console.error(errorMsg);
    alert(errorMsg);
    return false;
};

window.addEventListener('unhandledrejection', function(event) {
    var errorMsg = "捕获到 Promise 异常:\n" + event.reason;
    console.error(errorMsg);
    alert(errorMsg);
});

// 检查静态资源连通性
fetch('/health').then(function(r) {
    console.log("Backend connectivity: OK (" + r.status + ")");
}).catch(function(e) {
    console.error("Backend connectivity: FAIL", e);
    alert("无法连接到后端 API，请检查服务器是否在线。");
});
