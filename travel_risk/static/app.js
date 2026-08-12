/* 旅游风控系统 - 前端公共工具 */
async function apiFetch(url, options = {}) {
  const resp = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || `请求失败 (${resp.status})`);
  }
  return data;
}

function riskLevelClass(level) {
  if (level === "极高" || level === "拒绝") return "risk-high";
  if (level === "高" || level === "人工审核") return "risk-medium";
  return "risk-low";
}

function decisionBadge(decision) {
  const map = {
    "通过": "success", "标记": "info", "人工审核": "warning", "拒绝": "danger",
    "已通过": "success", "已拒绝": "danger", "已关闭": "secondary",
    "待审核": "warning", "审核中": "info",
  };
  const cls = map[decision] || "secondary";
  return `<span class="badge bg-${cls} badge-decision">${decision}</span>`;
}

function paginationBar(total, page, pageSize, onChange) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  let html = `<div class="d-flex justify-content-between align-items-center">
    <span class="text-muted small">共 ${total} 条 · 第 ${page}/${pages} 页</span>
    <div class="btn-group btn-group-sm">`;
  html += `<button class="btn btn-outline-secondary" onclick="${onChange}(${Math.max(1, page - 1)})" ${page <= 1 ? "disabled" : ""}>上一页</button>`;
  html += `<button class="btn btn-outline-secondary" onclick="${onChange}(${Math.min(pages, page + 1)})" ${page >= pages ? "disabled" : ""}>下一页</button>`;
  html += `</div></div>`;
  return html;
}

function formatTime(t) {
  if (!t) return "-";
  return String(t).replace("T", " ").slice(0, 19);
}

function showToast(message, type = "success") {
  const colors = { success: "#198754", error: "#dc3545", warning: "#fd7e14" };
  const el = document.createElement("div");
  el.style.cssText = `position:fixed;top:20px;right:20px;z-index:9999;background:${colors[type] || "#198754"};
    color:#fff;padding:12px 18px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.2);font-size:14px;`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}
