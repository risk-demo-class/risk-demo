const shell = document.getElementById("app-shell");
const currentPage = shell.dataset.page;
let authContext = null;
let dialogScrollY = 0;

const pageInfo = {
  dashboard: ["风险主面板", "订单风险态势与处置概览"],
  orders: ["订单中心", "查询四类 OTA 订单及风险详情"],
  orderDetail: ["订单详情", "风险证据、旅客信息与审核结果"],
  reviews: ["人工审核", "处理规则引擎送审的风险案件"],
  rules: ["规则管理", "按业务含义配置规则和风险档位"],
  blacklist: ["黑护照名单", "查询、添加和维护风险证件"],
  audit: ["审计日志", "追踪规则、名单和审核操作"],
  permissions: ["权限管理", "管理员工账号、角色和操作范围"],
  agent: ["管理 Agent", "使用自然语言查询和操作旅游风控数据库"],
};

const navigation = [
  ["dashboard", "/", "▦", "风险主面板", "dashboard:view"],
  ["orders", "/orders", "≡", "订单中心", "orders:view"],
  ["reviews", "/reviews", "✓", "人工审核", "reviews:view"],
  ["rules", "/rules", "⚙", "规则管理", "rules:view"],
  ["blacklist", "/blacklist", "⊘", "黑护照名单", "blacklist:view"],
  ["audit", "/audit", "◷", "审计日志", "audit:view"],
  ["permissions", "/permissions", "♙", "权限管理", "iam:view"],
  ["agent", "/agent", "✦", "管理 Agent", null, true],
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderAgentInline(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function agentTableCells(line) {
  let content = String(line || "").trim();
  if (content.startsWith("|")) content = content.slice(1);
  if (content.endsWith("|")) content = content.slice(0, -1);
  return content.split("|").map((cell) => cell.trim());
}

function isAgentTableDivider(line) {
  const cells = agentTableCells(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function renderAgentAnswer(markdown) {
  const lines = String(markdown || "").replaceAll("\r\n", "\n").split("\n");
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isAgentTableDivider(lines[index + 1])) {
      const headings = agentTableCells(line);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(agentTableCells(lines[index]));
        index += 1;
      }
      blocks.push(`<div class="agent-answer-table-wrap"><table class="agent-answer-table"><thead><tr>${headings.map((cell) => `<th>${renderAgentInline(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${headings.map((_, cellIndex) => `<td title="${escapeHtml(row[cellIndex] || "—")}">${renderAgentInline(row[cellIndex] || "—")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(`<ul>${items.map((item) => `<li>${renderAgentInline(item)}</li>`).join("")}</ul>`);
      continue;
    }

    const paragraph = [];
    while (index < lines.length && lines[index].trim()) {
      if (paragraph.length && lines[index].includes("|") && index + 1 < lines.length && isAgentTableDivider(lines[index + 1])) break;
      if (paragraph.length && /^\s*[-*]\s+/.test(lines[index])) break;
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(`<p>${paragraph.map(renderAgentInline).join("<br>")}</p>`);
  }
  return blocks.join("");
}

function labelType(value) {
  return { FLIGHT: "机票", HOTEL: "酒店", VISA: "签证", TOUR: "跟团游" }[value] || value || "—";
}

function labelDecision(value) {
  return { PASS: "放行", REVIEW: "人工审核", REJECT: "拒绝" }[value] || value || "—";
}

function labelStatus(value) {
  return {
    PENDING: "待审核", APPROVED: "已放行", REJECTED: "已拒绝",
    CANCELLED: "已取消", ACTIVE: "启用", INACTIVE: "停用",
  }[value] || value || "—";
}

function badge(value, kind = "decision") {
  const normalized = String(value || "").toLowerCase();
  const text = kind === "type" ? labelType(value) : kind === "status" ? labelStatus(value) : labelDecision(value);
  return `<span class="badge badge-${escapeHtml(normalized)}">${escapeHtml(text)}</span>`;
}

function formatMoney(value) {
  return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(`${String(value).slice(0, 10)}T00:00:00`));
}

function formatDateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(value));
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 401) {
    location.replace(`/login?next=${encodeURIComponent(location.pathname + location.search)}`);
    throw new Error("登录已失效，正在跳转");
  }
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") message = payload.detail;
      else if (Array.isArray(payload.detail)) {
        message = payload.detail.map((item) => String(item.msg || "输入内容不正确").replace(/^Value error,\s*/, "")).join("；");
      }
    } catch (_) { /* response is not JSON */ }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

function toast(message, type = "success") {
  const zone = document.getElementById("toast-zone");
  const item = document.createElement("div");
  item.className = `toast ${type}`;
  item.textContent = message;
  zone.appendChild(item);
  setTimeout(() => item.remove(), 3200);
}

function loading() {
  return `<div class="loading"><div><div class="loader"></div>正在读取风控数据…</div></div>`;
}

function empty(message = "暂无数据") {
  return `<div class="empty">${escapeHtml(message)}</div>`;
}

function fatal(error) {
  document.getElementById("page-content").innerHTML = `
    <div class="panel empty"><div><strong>页面加载失败</strong><p>${escapeHtml(error.message)}</p><button class="btn" onclick="location.reload()">重新加载</button></div></div>`;
}

function pagination(data, handlerName) {
  return `
    <div class="pagination">
      <span>共 ${formatNumber(data.total)} 条，第 ${data.page}/${data.pages} 页</span>
      <div class="pagination-buttons">
        <button class="btn btn-sm" data-page-target="${data.page - 1}" data-page-handler="${handlerName}" ${data.page <= 1 ? "disabled" : ""}>上一页</button>
        <button class="btn btn-sm" data-page-target="${data.page + 1}" data-page-handler="${handlerName}" ${data.page >= data.pages ? "disabled" : ""}>下一页</button>
      </div>
    </div>`;
}

const tableSort = {
  orders: { by: "order_time", order: "desc" },
  reviews: { by: "created_at", order: "desc" },
  blacklist: { by: "created_at", order: "desc" },
  audit: { by: "created_at", order: "desc" },
};

function sortableHeader(label, key, state, defaultOrder = "asc") {
  const active = state.by === key;
  const arrow = active ? (state.order === "asc" ? "↑" : "↓") : "↕";
  const nextOrder = active ? (state.order === "asc" ? "降序" : "升序") : (defaultOrder === "asc" ? "升序" : "降序");
  return `<th aria-sort="${active ? (state.order === "asc" ? "ascending" : "descending") : "none"}"><button class="sort-header ${active ? "active" : ""}" type="button" data-sort-key="${key}" data-default-order="${defaultOrder}" title="按${escapeHtml(label)}${nextOrder}排列"><span>${escapeHtml(label)}</span><span class="sort-arrow" aria-hidden="true">${arrow}</span></button></th>`;
}

function bindSortableHeaders(container, state, loader) {
  container.querySelectorAll("[data-sort-key]").forEach((button) => button.addEventListener("click", () => {
    const key = button.dataset.sortKey;
    if (state.by === key) state.order = state.order === "asc" ? "desc" : "asc";
    else {
      state.by = key;
      state.order = button.dataset.defaultOrder || "asc";
    }
    loader(1);
  }));
}

function hasPermission(code) {
  return Boolean(authContext?.permissions?.includes(code));
}

function isAdministrator() {
  return Boolean(authContext?.roles?.some((role) => role.role_code === "ADMINISTRATOR"));
}

function mountShell() {
  const info = pageInfo[currentPage] || pageInfo.dashboard;
  document.title = `${info[0]} · OTA 旅游风控平台`;
  shell.innerHTML = `
    <div class="app-layout">
      <aside class="sidebar" id="sidebar">
        <div class="brand"><div class="brand-mark">R</div><div><strong>旅盾 RiskOps</strong><small>OTA 风险运营平台</small></div></div>
        <div class="nav-label">工作台</div>
        <nav class="nav-list" aria-label="主导航">
          ${navigation.filter((item) => (item[4] ? hasPermission(item[4]) : true) && (!item[5] || isAdministrator())).map(([key, href, icon, text]) => `<a class="nav-item ${currentPage === key || (currentPage === "orderDetail" && key === "orders") ? "active" : ""}" href="${href}"><span class="nav-icon">${icon}</span><span>${text}</span></a>`).join("")}
        </nav>
        <div class="sidebar-foot"><div class="system-state"><span class="state-dot"></span><span>规则引擎运行正常</span></div></div>
      </aside>
      <section class="app-main">
        <header class="topbar">
          <div class="topbar-left">
            <button class="menu-button" id="menu-button" aria-label="打开导航">☰</button>
            <div><h1 class="page-title">${info[0]}</h1><p class="page-subtitle">${info[1]}</p></div>
          </div>
          <div class="operator"><div class="operator-avatar">${escapeHtml(authContext.username.slice(0, 1).toUpperCase())}</div><div class="operator-text"><div class="operator-name">${escapeHtml(authContext.username)}</div><div class="operator-role">${escapeHtml(authContext.roles?.map((item) => item.role_name).join("、") || authContext.display_name)}</div></div><button class="btn btn-sm" id="logout-button">退出</button></div>
        </header>
        <main class="content" id="page-content">${loading()}</main>
      </section>
    </div>
    <dialog class="dialog" id="app-dialog"></dialog>
    <div class="toast-zone" id="toast-zone" aria-live="polite"></div>`;
  const menu = document.getElementById("menu-button");
  menu.addEventListener("click", () => document.getElementById("sidebar").classList.toggle("open"));
  document.getElementById("app-dialog").addEventListener("close", unlockPageScroll);
  document.getElementById("logout-button").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" });
    location.replace("/login");
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-page-target]");
    if (!button || button.disabled) return;
    const handler = window[button.dataset.pageHandler];
    if (handler) handler(Number(button.dataset.pageTarget));
  });
}

function closeDialog() {
  const dialog = document.getElementById("app-dialog");
  if (dialog.open) dialog.close();
}

function lockPageScroll() {
  if (document.body.classList.contains("dialog-open")) return;
  dialogScrollY = window.scrollY;
  const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
  document.documentElement.style.setProperty("--scrollbar-width", `${Math.max(scrollbarWidth, 0)}px`);
  document.body.style.top = `-${dialogScrollY}px`;
  document.body.classList.add("dialog-open");
}

function unlockPageScroll() {
  if (!document.body.classList.contains("dialog-open")) return;
  document.body.classList.remove("dialog-open");
  document.body.style.removeProperty("top");
  document.documentElement.style.removeProperty("--scrollbar-width");
  window.scrollTo(0, dialogScrollY);
}

function showDialog(content, variant = "") {
  const dialog = document.getElementById("app-dialog");
  dialog.className = `dialog ${variant}`.trim();
  dialog.innerHTML = content;
  dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", closeDialog));
  lockPageScroll();
  dialog.showModal();
}

function decisionColor(score) {
  if (score >= 75) return "#ef4444";
  if (score >= 30) return "#f59e0b";
  return "#22c55e";
}

async function renderDashboard() {
  const root = document.getElementById("page-content");
  const data = await api("/api/dashboard");
  const total = Object.values(data.decisions).reduce((sum, value) => sum + value, 0) || 1;
  const passDeg = (data.decisions.PASS || 0) / total * 360;
  const reviewDeg = (data.decisions.REVIEW || 0) / total * 360;
  const maxType = Math.max(...data.order_types.map((item) => item.count), 1);
  const maxTrend = Math.max(...data.trend.map((item) => item.orders), 1);
  root.innerHTML = `
    <div class="page-head"><div><h2>今日风险态势</h2><p>基于当前规则与 XGBoost 模型融合后的订单评估结果</p></div>${hasPermission("reviews:view") ? '<a class="btn" href="/reviews">进入审核队列</a>' : ""}</div>
    <section class="stats-grid">
      <article class="stat-card"><div class="stat-label">累计订单</div><div class="stat-value">${formatNumber(data.summary.total_orders)}</div><div class="stat-note">四类业务统一监控</div></article>
      <article class="stat-card"><div class="stat-label">交易总额</div><div class="stat-value">${formatMoney(data.summary.total_amount)}</div><div class="stat-note">风险相关金额 <strong>${formatMoney(data.summary.risk_amount)}</strong></div></article>
      <article class="stat-card"><div class="stat-label">待审核案件</div><div class="stat-value">${formatNumber(data.summary.pending_reviews)}</div><div class="stat-note">需要风控人员处置</div></article>
      <article class="stat-card"><div class="stat-label">自动拒绝率</div><div class="stat-value">${data.summary.reject_rate}%</div><div class="stat-note">累计拒绝 <strong>${formatNumber(data.decisions.REJECT || 0)}</strong> 笔</div></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel"><div class="panel-header"><div class="panel-title">近 14 天订单趋势</div><div class="panel-note">订单量 / 风险拒绝</div></div>
        <div class="trend-chart">${data.trend.map((item, index) => `
          <div class="trend-bar-group" title="${formatDate(item.date)} · ${item.orders} 笔">
            <div class="trend-bar" style="height:${Math.max(item.orders / maxTrend * 100, 3)}%"></div>
            <div class="trend-bar risk" style="height:${Math.max(item.rejected / maxTrend * 100, item.rejected ? 3 : 0)}%"></div>
            ${(index % 2 === 0 || data.trend.length < 9) ? `<span class="trend-label">${String(item.date).slice(5)}</span>` : ""}
          </div>`).join("")}</div>
      </article>
      <article class="panel"><div class="panel-header"><div class="panel-title">决策分布</div><div class="panel-note">累计订单</div></div>
        <div class="donut-wrap"><div class="donut" style="--pass:${passDeg}deg;--review:${reviewDeg}deg"><div class="donut-center"><strong>${formatNumber(total)}</strong><span>评估订单</span></div></div></div>
        <div class="legend"><span class="legend-item"><i class="legend-dot" style="background:#22c55e"></i>放行 ${data.decisions.PASS || 0}</span><span class="legend-item"><i class="legend-dot" style="background:#f59e0b"></i>审核 ${data.decisions.REVIEW || 0}</span><span class="legend-item"><i class="legend-dot" style="background:#ef4444"></i>拒绝 ${data.decisions.REJECT || 0}</span></div>
      </article>
    </section>
    <section class="dashboard-grid equal">
      <article class="panel"><div class="panel-header"><div class="panel-title">业务订单分布</div><div class="panel-note">订单量与金额</div></div><div class="type-bars">
        ${data.order_types.map((item) => `<div><div class="type-row-head"><span>${labelType(item.order_type)}</span><span>${item.count} 笔 · ${formatMoney(item.amount)}</span></div><div class="bar-track"><div class="bar-fill" style="width:${item.count / maxType * 100}%"></div></div></div>`).join("")}
      </div></article>
      <article class="panel"><div class="panel-header"><div class="panel-title">高频命中规则</div><a class="link" href="/rules">管理规则</a></div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>规则</th><th>编码</th><th>命中</th></tr></thead><tbody>${data.top_rules.map((item) => `<tr><td class="strong">${escapeHtml(item.rule_name)}</td><td class="mono muted">${escapeHtml(item.rule_code)}</td><td class="strong">${item.hit_count}</td></tr>`).join("")}</tbody></table></div>
      </article>
    </section>
    <section class="panel"><div class="panel-header"><div class="panel-title">最新订单</div><a class="link" href="/orders">查看全部</a></div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>订单号</th><th>用户</th><th>业务</th><th>金额</th><th>时间</th><th>风险分</th><th>决策</th></tr></thead><tbody>
      ${data.recent_orders.map((item) => `<tr><td>${hasPermission("orders:view") ? `<a class="link mono" href="/orders/${item.order_id}">${escapeHtml(item.order_no)}</a>` : `<span class="mono">${escapeHtml(item.order_no)}</span>`}</td><td>${escapeHtml(item.user_name)}</td><td>${badge(item.order_type, "type")}</td><td class="money">${formatMoney(item.total_amount)}</td><td class="nowrap muted">${formatDateTime(item.order_time)}</td><td class="strong">${item.risk_score}</td><td>${badge(item.decision)}</td></tr>`).join("")}
      </tbody></table></div>
    </section>`;
}

async function renderOrders() {
  const root = document.getElementById("page-content");
  root.innerHTML = `
    <div class="page-head"><div><h2>全量订单</h2><p>覆盖机票、酒店、签证与跟团游业务</p></div></div>
    <section class="panel">
      <form class="filters" id="order-filters">
        <div class="field search-field"><label for="order-q">订单号或用户名</label><input class="input" id="order-q" name="q" placeholder="输入关键词"></div>
        <div class="field filter-field"><label for="order-type">业务类型</label><select class="select" id="order-type" name="order_type"><option value="">全部业务</option><option value="FLIGHT">机票</option><option value="HOTEL">酒店</option><option value="VISA">签证</option><option value="TOUR">跟团游</option></select></div>
        <div class="field filter-field"><label for="order-decision">风险决策</label><select class="select" id="order-decision" name="decision"><option value="">全部决策</option><option value="PASS">放行</option><option value="REVIEW">人工审核</option><option value="REJECT">拒绝</option></select></div>
        <div class="field"><label>&nbsp;</label><button class="btn btn-primary" type="submit">查询订单</button></div>
      </form>
      <div id="orders-result">${loading()}</div>
    </section>`;
  document.getElementById("order-filters").addEventListener("submit", (event) => { event.preventDefault(); loadOrders(1); });
  window.loadOrders = loadOrders;
  await loadOrders(1);
}

async function loadOrders(page = 1) {
  const result = document.getElementById("orders-result");
  result.innerHTML = loading();
  const params = new URLSearchParams({ page, page_size: 20 });
  const q = document.getElementById("order-q").value.trim();
  const type = document.getElementById("order-type").value;
  const decision = document.getElementById("order-decision").value;
  if (q) params.set("q", q);
  if (type) params.set("order_type", type);
  if (decision) params.set("decision", decision);
  params.set("sort_by", tableSort.orders.by);
  params.set("sort_order", tableSort.orders.order);
  const data = await api(`/api/orders?${params}`);
  result.innerHTML = data.items.length ? `
    <div class="table-wrap"><table class="data-table stable-table orders-table"><colgroup>${"<col>".repeat(9)}</colgroup><thead><tr>${sortableHeader("订单号", "order_no", tableSort.orders)}${sortableHeader("用户", "user_name", tableSort.orders)}${sortableHeader("业务", "order_type", tableSort.orders)}${sortableHeader("目的地", "dest_country", tableSort.orders)}${sortableHeader("金额", "total_amount", tableSort.orders, "desc")}${sortableHeader("出行人数", "passenger_count", tableSort.orders, "desc")}${sortableHeader("风险分", "risk_score", tableSort.orders, "desc")}${sortableHeader("决策", "decision", tableSort.orders)}${sortableHeader("下单时间", "order_time", tableSort.orders, "desc")}</tr></thead><tbody>
      ${data.items.map((item) => `<tr><td><a class="link mono" href="/orders/${item.order_id}" title="${escapeHtml(item.order_no)}">${escapeHtml(item.order_no)}</a></td><td title="${escapeHtml(item.user_name)}">${escapeHtml(item.user_name)}</td><td>${badge(item.order_type, "type")}</td><td title="${escapeHtml(item.dest_country || "境内")}">${escapeHtml(item.dest_country || "境内")}</td><td class="money" title="${formatMoney(item.total_amount)}">${formatMoney(item.total_amount)}</td><td>${item.passenger_count}</td><td class="strong">${item.risk_score}</td><td>${badge(item.decision)}</td><td class="nowrap muted" title="${formatDateTime(item.order_time)}">${formatDateTime(item.order_time)}</td></tr>`).join("")}
    </tbody></table></div>${pagination(data, "loadOrders")}` : empty("没有符合条件的订单");
  bindSortableHeaders(result, tableSort.orders, loadOrders);
}

function renderObjectRows(data) {
  if (Array.isArray(data)) return data.map((item, index) => `<div class="hit-card"><div class="hit-name">记录 ${index + 1}</div><div class="hit-evidence">${escapeHtml(JSON.stringify(item))}</div></div>`).join("");
  if (!data) return empty("暂无业务扩展信息");
  return `<dl class="kv-grid">${Object.entries(data).map(([key, value]) => `<div class="kv"><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value ?? "—")}</dd></div>`).join("")}</dl>`;
}

async function renderOrderDetail() {
  const root = document.getElementById("page-content");
  const orderId = location.pathname.split("/").filter(Boolean).at(-1);
  const data = await api(`/api/orders/${orderId}`);
  const order = data.order;
  root.innerHTML = `
    <a class="back-link" href="/orders">← 返回订单中心</a>
    <section class="panel detail-hero">
      <div><h2 class="detail-title">${escapeHtml(order.order_no)}</h2><div class="detail-meta">${badge(order.order_type, "type")}${badge(order.decision)}<span>${escapeHtml(order.user_name)}</span><span>${formatDateTime(order.order_time)}</span></div><p class="muted">${escapeHtml(order.decision_reason || "")}</p></div>
      <div class="score-ring" style="--score:${order.risk_score};--score-color:${decisionColor(order.risk_score)}"><div><strong>${order.risk_score}</strong><span>风险评分</span></div></div>
    </section>
    <section class="detail-grid">
      <article class="panel"><div class="panel-header"><div class="panel-title">订单信息</div></div><dl class="kv-grid">
        <div class="kv"><dt>订单金额</dt><dd>${formatMoney(order.total_amount)}</dd></div><div class="kv"><dt>目的国家</dt><dd>${escapeHtml(order.dest_country || "中国")}</dd></div>
        <div class="kv"><dt>出发日期</dt><dd>${formatDate(order.depart_date)}</dd></div><div class="kv"><dt>出行人数</dt><dd>${order.passenger_count} 人</dd></div>
        <div class="kv"><dt>跨境订单</dt><dd>${order.is_cross_border ? "是" : "否"}</dd></div><div class="kv"><dt>订单状态</dt><dd>${escapeHtml(order.order_status)}</dd></div>
      </dl></article>
      <article class="panel"><div class="panel-header"><div class="panel-title">用户与支付</div></div><dl class="kv-grid">
        <div class="kv"><dt>用户名</dt><dd>${escapeHtml(data.user.name)}</dd></div><div class="kv"><dt>实名状态</dt><dd>${data.user.real_name_status ? "已实名" : "未实名"}</dd></div>
        <div class="kv"><dt>账号年龄</dt><dd>${data.user.account_age_days} 天</dd></div><div class="kv"><dt>会员等级</dt><dd>${escapeHtml(data.user.vip_level)}</dd></div>
        <div class="kv"><dt>支付方式</dt><dd>${escapeHtml(data.payment.account_type)}</dd></div><div class="kv"><dt>支付账号状态</dt><dd>${escapeHtml(data.payment.status)}</dd></div>
      </dl></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel"><div class="panel-header"><div class="panel-title">规则命中证据</div><div class="panel-note">规则分 ${data.assessment.raw_score} · 模型分 ${data.assessment.model_score ?? "未启用"} · 最终分 ${data.assessment.risk_score}</div></div>
        <div class="hit-list">${data.hits.length ? data.hits.map((hit) => `<div class="hit-card"><div class="hit-head"><div><div class="hit-name">${escapeHtml(hit.rule_name)}</div><div class="rule-code mono">${escapeHtml(hit.rule_code)}</div></div><div class="hit-score">+${hit.score}</div></div><div class="hit-evidence">${escapeHtml(JSON.stringify(hit.evidence))}</div></div>`).join("") : empty("该订单未命中风险规则")}</div>
      </article>
      <article class="panel"><div class="panel-header"><div class="panel-title">审核状态</div></div>
        ${data.review_case ? `<dl class="kv-grid"><div class="kv"><dt>案件编号</dt><dd>${escapeHtml(data.review_case.case_no)}</dd></div><div class="kv"><dt>案件状态</dt><dd>${badge(data.review_case.status, "status")}</dd></div><div class="kv"><dt>审核人</dt><dd>${escapeHtml(data.review_case.reviewer || "待分配")}</dd></div><div class="kv"><dt>审核时间</dt><dd>${formatDateTime(data.review_case.reviewed_at)}</dd></div><div class="kv" style="grid-column:1/-1"><dt>处置原因</dt><dd>${escapeHtml(data.review_case.decision_reason || "待审核")}</dd></div></dl>${data.review_case.status === "PENDING" && hasPermission("reviews:decide") ? `<div class="actions" style="margin-top:16px"><button class="btn btn-primary" id="detail-review-action">立即处置</button></div>` : ""}` : empty("该订单无需人工审核")}
      </article>
    </section>
    <section class="detail-grid">
      <article class="panel"><div class="panel-header"><div class="panel-title">出行人信息</div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>姓名</th><th>角色</th><th>证件</th><th>国籍</th></tr></thead><tbody>${data.passengers.map((item) => `<tr><td class="strong">${escapeHtml(item.name)}</td><td>${escapeHtml(item.passenger_role)}</td><td class="mono">${escapeHtml(item.id_number_masked)}</td><td>${escapeHtml(item.nationality)}</td></tr>`).join("")}</tbody></table></div></article>
      <article class="panel"><div class="panel-header"><div class="panel-title">${labelType(order.order_type)}业务信息</div></div>${renderObjectRows(data.product_detail)}</article>
    </section>`;
  if (data.review_case?.status === "PENDING" && hasPermission("reviews:decide")) document.getElementById("detail-review-action").addEventListener("click", () => openReviewDialog(data.review_case.case_id, order.order_no, order.risk_score, () => location.reload()));
}

function openReviewDialog(caseId, orderNo, riskScore, onSuccess) {
  showDialog(`
    <div class="dialog-head"><h3>审核风险订单</h3><button class="dialog-close" data-close-dialog aria-label="关闭">×</button></div>
    <div class="dialog-body"><div class="kv-grid"><div class="kv"><dt>订单号</dt><dd>${escapeHtml(orderNo)}</dd></div><div class="kv"><dt>风险评分</dt><dd>${riskScore}</dd></div></div><div class="field"><label for="review-reason">处置原因</label><textarea class="textarea" id="review-reason" placeholder="请填写核验结论和处置依据"></textarea></div></div>
    <div class="dialog-foot"><button class="btn" data-close-dialog>取消</button><button class="btn btn-danger" id="review-reject">拒绝订单</button><button class="btn btn-success" id="review-approve">确认放行</button></div>`);
  const submit = async (decision) => {
    const reason = document.getElementById("review-reason").value.trim();
    if (reason.length < 2) return toast("请填写处置原因", "error");
    try {
      await api(`/api/reviews/${caseId}/decision`, { method: "POST", body: JSON.stringify({ decision, reason }) });
      closeDialog(); toast("审核结果已提交"); if (onSuccess) onSuccess();
    } catch (error) { toast(error.message, "error"); }
  };
  document.getElementById("review-reject").addEventListener("click", () => submit("REJECTED"));
  document.getElementById("review-approve").addEventListener("click", () => submit("APPROVED"));
}

async function renderReviews() {
  const root = document.getElementById("page-content");
  root.innerHTML = `
    <div class="page-head"><div><h2>审核案件队列</h2><p>处置操作将以当前登录账号留痕</p></div></div>
    <section class="panel"><form class="filters" id="review-filters"><div class="field filter-field"><label for="review-status">案件状态</label><select class="select" id="review-status"><option value="">全部状态</option><option value="PENDING" selected>待审核</option><option value="APPROVED">已放行</option><option value="REJECTED">已拒绝</option><option value="CANCELLED">重算后取消</option></select></div><div class="field"><label>&nbsp;</label><button class="btn btn-primary">筛选</button></div></form><div id="reviews-result">${loading()}</div></section>`;
  document.getElementById("review-filters").addEventListener("submit", (event) => { event.preventDefault(); loadReviews(1); });
  window.loadReviews = loadReviews;
  await loadReviews(1);
}

async function loadReviews(page = 1) {
  const result = document.getElementById("reviews-result");
  result.innerHTML = loading();
  const params = new URLSearchParams({ page, page_size: 20, sort_by: tableSort.reviews.by, sort_order: tableSort.reviews.order });
  const status = document.getElementById("review-status").value;
  if (status) params.set("status", status);
  const data = await api(`/api/reviews?${params}`);
  result.innerHTML = data.items.length ? `<div class="table-wrap"><table class="data-table stable-table reviews-table"><colgroup>${"<col>".repeat(9)}</colgroup><thead><tr>${sortableHeader("案件编号", "case_no", tableSort.reviews)}${sortableHeader("订单", "order_no", tableSort.reviews)}${sortableHeader("用户", "user_name", tableSort.reviews)}${sortableHeader("业务", "order_type", tableSort.reviews)}${sortableHeader("金额", "total_amount", tableSort.reviews, "desc")}${sortableHeader("风险分", "risk_score", tableSort.reviews, "desc")}${sortableHeader("状态", "status", tableSort.reviews)}${sortableHeader("入队时间", "created_at", tableSort.reviews, "desc")}<th>操作</th></tr></thead><tbody>${data.items.map((item) => `<tr><td class="mono" title="${escapeHtml(item.case_no)}">${escapeHtml(item.case_no)}</td><td>${hasPermission("orders:view") ? `<a class="link mono" href="/orders/${item.order_id}" title="${escapeHtml(item.order_no)}">${escapeHtml(item.order_no)}</a>` : `<span class="mono" title="${escapeHtml(item.order_no)}">${escapeHtml(item.order_no)}</span>`}</td><td title="${escapeHtml(item.user_name)}">${escapeHtml(item.user_name)}</td><td>${badge(item.order_type, "type")}</td><td class="money" title="${formatMoney(item.total_amount)}">${formatMoney(item.total_amount)}</td><td class="strong">${item.risk_score}</td><td>${badge(item.status, "status")}</td><td class="nowrap muted" title="${formatDateTime(item.created_at)}">${formatDateTime(item.created_at)}</td><td>${item.status === "PENDING" && hasPermission("reviews:decide") ? `<button class="btn btn-sm btn-primary review-action" data-case="${item.case_id}" data-order="${escapeHtml(item.order_no)}" data-score="${item.risk_score}">审核</button>` : `<span class="muted" title="${escapeHtml(item.reviewer || (item.status === "PENDING" ? "只读" : "—"))}">${escapeHtml(item.reviewer || (item.status === "PENDING" ? "只读" : "—"))}</span>`}</td></tr>`).join("")}</tbody></table></div>${pagination(data, "loadReviews")}` : empty("当前筛选条件下没有审核案件");
  bindSortableHeaders(result, tableSort.reviews, loadReviews);
  result.querySelectorAll(".review-action").forEach((button) => button.addEventListener("click", () => openReviewDialog(button.dataset.case, button.dataset.order, button.dataset.score, () => loadReviews(page))));
}

async function renderRules() {
  const root = document.getElementById("page-content");
  root.innerHTML = `<div class="page-head"><div><h2>风险规则</h2><p>同名条件已合并展示；保存规则后会自动重新评估全部订单</p></div></div><div id="rules-result">${loading()}</div>`;
  await loadRules();
}

const ruleConditionFields = {
  VISA_REJECT_HISTORY: [
    ["window_days", "统计周期", [30, 60, 90, 180], (v) => `最近 ${v} 天`],
    ["threshold", "拒签次数", [1, 2, 3, 4, 5], (v) => `不少于 ${v} 次`],
  ],
  VISA_MULTI_COUNTRY: [
    ["window_days", "统计周期", [7, 15, 30, 60], (v) => `最近 ${v} 天`],
    ["threshold", "国家数量", [1, 2, 3, 4, 5], (v) => `不少于 ${v} 个`],
  ],
  CROSS_BORDER_LARGE_AMOUNT: [
    ["threshold", "订单金额", [10000, 20000, 30000, 50000, 80000, 100000], (v) => `不少于 ${formatMoney(v)}`],
  ],
  FLIGHT_TICKET_HOARDING: [
    ["window_hours", "统计周期", [1, 2, 3, 6], (v) => `最近 ${v} 小时`],
    ["threshold", "同航班票数", [2, 3, 4, 5, 6, 8, 10], (v) => `不少于 ${v} 张`],
  ],
  NIGHT_RUSH_ORDER: [
    ["hour_start", "夜间开始", [0, 1, 2, 3, 4], (v) => `${String(v).padStart(2, "0")}:00`],
    ["hour_end_exclusive", "夜间结束", [1, 2, 3, 4, 5, 6], (v) => `${String(v).padStart(2, "0")}:00`],
    ["interval_days_lte", "最晚出发", [1, 3, 5, 7, 14], (v) => `${v} 天内`],
  ],
  PASSENGER_INFO_MISMATCH: [
    ["threshold_percent", "历史信息匹配率", [10, 20, 30, 40, 50], (v) => `不高于 ${v}%`],
  ],
  NEW_USER_LARGE_ORDER: [
    ["account_age_days_lt", "账号注册时长", [1, 3, 7, 14, 30], (v) => `少于 ${v} 天`],
    ["amount_gt", "订单金额", [5000, 10000, 20000, 30000, 50000], (v) => `高于 ${formatMoney(v)}`],
  ],
  PASSPORT_BLACKLIST: [
    ["entry_type", "名单类型", ["PASSPORT"], () => "护照黑名单"],
  ],
};

function selectOptions(values, current, formatter = (value) => value) {
  const options = [...values];
  if (!options.some((value) => String(value) === String(current))) options.push(current);
  return options.map((value) => `<option value="${escapeHtml(value)}" ${String(value) === String(current) ? "selected" : ""}>${escapeHtml(formatter(value))}</option>`).join("");
}

function conditionSummary(groupCode, condition) {
  const c = condition || {};
  const summaries = {
    VISA_REJECT_HISTORY: `最近 ${c.window_days} 天拒签不少于 ${c.threshold} 次`,
    VISA_MULTI_COUNTRY: `最近 ${c.window_days} 天申请不少于 ${c.threshold} 个国家`,
    CROSS_BORDER_LARGE_AMOUNT: `跨境订单金额不少于 ${formatMoney(c.threshold)}`,
    FLIGHT_TICKET_HOARDING: `最近 ${c.window_hours} 小时同支付账户、同航班购票不少于 ${c.threshold} 张`,
    NIGHT_RUSH_ORDER: `${String(c.hour_start).padStart(2, "0")}:00–${String(c.hour_end_exclusive).padStart(2, "0")}:00 下单，且 ${c.interval_days_lte} 天内出发`,
    PASSENGER_INFO_MISMATCH: `历史旅客信息匹配率不高于 ${c.threshold_percent}%`,
    NEW_USER_LARGE_ORDER: `注册少于 ${c.account_age_days_lt} 天，订单金额高于 ${formatMoney(c.amount_gt)}`,
    PASSPORT_BLACKLIST: "旅客护照命中有效黑名单",
  };
  return summaries[groupCode] || "已配置业务判断条件";
}

async function loadRules() {
  const result = document.getElementById("rules-result");
  const data = await api("/api/rule-groups");
  result.innerHTML = `<div class="rule-grid">${data.items.map((group) => `<article class="rule-card rule-group-card"><div class="rule-card-head"><div><div class="rule-name">${escapeHtml(group.rule_name)}</div><div class="muted">${group.tiers.length} 个风险档位 · ${group.applicable_order_types.map(labelType).join(" / ")}</div></div><span class="badge ${group.is_enabled ? "badge-active" : "badge-inactive"}">${group.is_enabled ? "启用" : "停用"}</span></div><div class="tier-list">${group.tiers.map((tier, index) => `<div class="tier-summary"><span><strong>${group.tiers.length > 1 ? (index === 0 ? "高风险" : "一般风险") : "风险条件"}</strong><small>${escapeHtml(conditionSummary(group.group_code, tier.condition_json))}</small></span><b>${tier.risk_score}<small>分</small></b></div>`).join("")}</div><div class="rule-action"><button class="btn btn-sm rule-edit" data-group="${escapeHtml(group.group_code)}" ${hasPermission("rules:manage") ? "" : "disabled"}>编辑规则档位</button></div></article>`).join("")}</div>`;
  result.querySelectorAll(".rule-edit").forEach((button) => button.addEventListener("click", () => openRuleDialog(data.items.find((item) => item.group_code === button.dataset.group))));
}

function openRuleDialog(group) {
  const fields = ruleConditionFields[group.group_code] || [];
  showDialog(`<div class="dialog-head"><div><h3>编辑规则档位</h3><p>${escapeHtml(group.rule_name)}</p></div><button class="dialog-close" data-close-dialog>×</button></div><div class="dialog-body">
    <div class="field"><label>规则状态</label><label class="check"><input type="checkbox" id="rule-enabled" ${group.is_enabled ? "checked" : ""}>启用此规则及全部档位</label></div>
    <div class="field"><label>适用业务</label><div class="checkbox-grid">${["FLIGHT","HOTEL","VISA","TOUR"].map((type) => `<label class="check"><input type="checkbox" name="rule-type" value="${type}" ${group.applicable_order_types.includes(type) ? "checked" : ""}>${labelType(type)}</label>`).join("")}</div></div>
    <div class="rule-tier-editor">${group.tiers.map((tier, index) => `<section class="tier-editor"><div class="tier-editor-title"><strong>${group.tiers.length > 1 ? (index === 0 ? "高风险档位" : "一般风险档位") : "风险档位"}</strong><span>命中后计分</span></div><div class="condition-grid">${fields.map(([key, label, values, formatter]) => `<div class="field"><label for="tier-${tier.rule_id}-${key}">${label}</label><select class="select tier-condition" id="tier-${tier.rule_id}-${key}" data-rule-id="${tier.rule_id}" data-key="${key}">${selectOptions(values, tier.condition_json[key], formatter)}</select></div>`).join("")}<div class="field"><label for="tier-${tier.rule_id}-score">风险分值</label><select class="select tier-score" id="tier-${tier.rule_id}-score" data-rule-id="${tier.rule_id}">${selectOptions(Array.from({length: 21}, (_, i) => i * 5), tier.risk_score, (v) => `${v} 分`)}</select></div></div><p class="condition-preview">${escapeHtml(conditionSummary(group.group_code, tier.condition_json))}</p></section>`).join("")}</div>
  </div><div class="dialog-foot"><button class="btn" data-close-dialog>取消</button><button class="btn btn-primary" id="rule-save">保存并重算评分</button></div>`);
  document.getElementById("rule-save").addEventListener("click", async () => {
    const saveButton = document.getElementById("rule-save");
    try {
      const types = [...document.querySelectorAll("[name=rule-type]:checked")].map((item) => item.value);
      if (!types.length) return toast("请至少选择一种适用业务", "error");
      const tiers = group.tiers.map((tier) => {
        const condition = { ...tier.condition_json };
        document.querySelectorAll(`.tier-condition[data-rule-id="${tier.rule_id}"]`).forEach((select) => {
          condition[select.dataset.key] = select.dataset.key === "entry_type" ? select.value : Number(select.value);
        });
        return { rule_id: tier.rule_id, risk_score: Number(document.querySelector(`.tier-score[data-rule-id="${tier.rule_id}"]`).value), condition_json: condition };
      });
      const payload = { is_enabled: document.getElementById("rule-enabled").checked, applicable_order_types: types, tiers };
      saveButton.disabled = true;
      saveButton.textContent = "正在保存并重算…";
      const response = await api(`/api/rule-groups/${encodeURIComponent(group.group_code)}`, { method: "PATCH", body: JSON.stringify(payload) });
      const summary = response.recalculation;
      closeDialog();
      toast(summary ? `规则已保存：重算 ${summary.total_orders} 笔，${summary.changed_assessments} 笔评分发生变化` : "规则配置已保存");
      await loadRules();
    } catch (error) {
      saveButton.disabled = false;
      saveButton.textContent = "保存并重算评分";
      toast(error.message, "error");
    }
  });
}

async function renderBlacklist() {
  const root = document.getElementById("page-content");
  root.innerHTML = `<div class="page-head"><div><h2>风险证件名单</h2><p>系统只保存证件哈希和掩码，不保存明文</p></div>${hasPermission("blacklist:manage") ? '<button class="btn btn-primary" id="blacklist-add">添加黑护照</button>' : ""}</div><section class="panel"><form class="filters" id="blacklist-filters"><div class="field search-field"><label for="blacklist-q">掩码或原因</label><input class="input" id="blacklist-q" placeholder="输入关键词"></div><div class="field filter-field"><label for="blacklist-status">状态</label><select class="select" id="blacklist-status"><option value="">全部</option><option value="ACTIVE">启用</option><option value="INACTIVE">停用</option></select></div><div class="field"><label>&nbsp;</label><button class="btn btn-primary">查询</button></div></form><div id="blacklist-result">${loading()}</div></section>`;
  document.getElementById("blacklist-add")?.addEventListener("click", openBlacklistCreateDialog);
  document.getElementById("blacklist-filters").addEventListener("submit", (event) => { event.preventDefault(); loadBlacklist(1); });
  window.loadBlacklist = loadBlacklist;
  await loadBlacklist(1);
}

async function loadBlacklist(page = 1) {
  const result = document.getElementById("blacklist-result");
  result.innerHTML = loading();
  const params = new URLSearchParams({ page, page_size: 20, sort_by: tableSort.blacklist.by, sort_order: tableSort.blacklist.order });
  const q = document.getElementById("blacklist-q").value.trim(); const status = document.getElementById("blacklist-status").value;
  if (q) params.set("q", q); if (status) params.set("status", status);
  const data = await api(`/api/blacklist?${params}`);
  result.innerHTML = data.items.length ? `<div class="table-wrap"><table class="data-table stable-table blacklist-table"><colgroup>${"<col>".repeat(7)}</colgroup><thead><tr>${sortableHeader("名单编号", "entry_id", tableSort.blacklist, "desc")}${sortableHeader("证件掩码", "value_masked", tableSort.blacklist)}${sortableHeader("原因", "reason", tableSort.blacklist)}${sortableHeader("状态", "status", tableSort.blacklist)}${sortableHeader("生效时间", "effective_at", tableSort.blacklist, "desc")}${sortableHeader("失效时间", "expire_at", tableSort.blacklist, "desc")}<th>操作</th></tr></thead><tbody>${data.items.map((item) => `<tr><td class="mono" title="BL-${String(item.entry_id).padStart(6,"0")}">BL-${String(item.entry_id).padStart(6,"0")}</td><td class="mono strong" title="${escapeHtml(item.value_masked)}">${escapeHtml(item.value_masked)}</td><td title="${escapeHtml(item.reason)}">${escapeHtml(item.reason)}</td><td>${badge(item.status, "status")}</td><td class="nowrap muted" title="${formatDateTime(item.effective_at)}">${formatDateTime(item.effective_at)}</td><td class="nowrap muted" title="${formatDateTime(item.expire_at)}">${formatDateTime(item.expire_at)}</td><td>${hasPermission("blacklist:manage") ? `<div class="actions"><button class="btn btn-sm blacklist-toggle" data-id="${item.entry_id}" data-status="${item.status}">${item.status === "ACTIVE" ? "停用" : "启用"}</button><button class="btn btn-sm blacklist-delete" data-id="${item.entry_id}">删除</button></div>` : '<span class="muted">只读</span>'}</td></tr>`).join("")}</tbody></table></div>${pagination(data, "loadBlacklist")}` : empty("没有符合条件的名单记录");
  bindSortableHeaders(result, tableSort.blacklist, loadBlacklist);
  result.querySelectorAll(".blacklist-toggle").forEach((button) => button.addEventListener("click", async () => { try { await api(`/api/blacklist/${button.dataset.id}`, { method: "PATCH", body: JSON.stringify({ status: button.dataset.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }) }); toast("名单状态已更新"); await loadBlacklist(page); } catch (error) { toast(error.message, "error"); } }));
  result.querySelectorAll(".blacklist-delete").forEach((button) => button.addEventListener("click", async () => { if (!confirm("确认删除这条名单记录？历史风险命中快照不会受影响。")) return; try { await api(`/api/blacklist/${button.dataset.id}`, { method: "DELETE" }); toast("名单记录已删除"); await loadBlacklist(page); } catch (error) { toast(error.message, "error"); } }));
}

function openBlacklistCreateDialog() {
  showDialog(`<div class="dialog-head"><h3>添加黑护照</h3><button class="dialog-close" data-close-dialog>×</button></div><div class="dialog-body"><div class="field"><label for="blacklist-document">护照号码</label><input class="input mono" id="blacklist-document" autocomplete="off" placeholder="仅用于生成哈希，系统不保存明文"></div><div class="field"><label for="blacklist-reason">加入原因</label><textarea class="textarea" id="blacklist-reason" placeholder="填写风险依据"></textarea></div><div class="field"><label for="blacklist-expire">失效时间（可选）</label><input class="input" type="datetime-local" id="blacklist-expire"></div></div><div class="dialog-foot"><button class="btn" data-close-dialog>取消</button><button class="btn btn-primary" id="blacklist-save">确认添加</button></div>`);
  document.getElementById("blacklist-save").addEventListener("click", async () => {
    const documentNumber = document.getElementById("blacklist-document").value.trim(); const reason = document.getElementById("blacklist-reason").value.trim(); const expire = document.getElementById("blacklist-expire").value;
    if (documentNumber.length < 4 || reason.length < 2) return toast("请完整填写护照号码和加入原因", "error");
    try { await api("/api/blacklist", { method: "POST", body: JSON.stringify({ document_number: documentNumber, reason, expire_at: expire || null }) }); closeDialog(); toast("黑护照已加入名单"); await loadBlacklist(1); } catch (error) { toast(error.message, "error"); }
  });
}

let iamData = null;

async function renderPermissions() {
  const root = document.getElementById("page-content");
  root.innerHTML = `<div class="page-head"><div><h2>员工与权限</h2><p>通过角色统一分配页面访问和操作权限</p></div></div><div id="iam-result">${loading()}</div>`;
  await loadIam();
}

async function loadIam() {
  iamData = await api("/api/iam/overview");
  const root = document.getElementById("iam-result");
  root.innerHTML = `<div class="iam-tabs"><button class="btn btn-primary iam-tab" data-tab="users">员工账号</button><button class="btn iam-tab" data-tab="roles">角色权限</button></div><div id="iam-panel"></div>`;
  root.querySelectorAll(".iam-tab").forEach((button) => button.addEventListener("click", () => {
    root.querySelectorAll(".iam-tab").forEach((item) => item.classList.toggle("btn-primary", item === button));
    renderIamPanel(button.dataset.tab);
  }));
  renderIamPanel("users");
}

function renderIamPanel(tab) {
  const panel = document.getElementById("iam-panel");
  if (tab === "users") {
    panel.innerHTML = `<section class="panel"><div class="panel-header"><div><div class="panel-title">员工账号</div><div class="panel-note">停用账号会立即使其登录失效</div></div>${iamData.can_manage ? '<button class="btn btn-primary" id="iam-user-add">新建员工</button>' : ""}</div><div class="table-wrap"><table class="data-table"><thead><tr><th>员工</th><th>账号</th><th>角色</th><th>状态</th><th>最近登录</th><th>操作</th></tr></thead><tbody>${iamData.users.map((user) => `<tr><td class="strong">${escapeHtml(user.display_name)}</td><td class="mono">${escapeHtml(user.username)}</td><td>${user.roles.length ? user.roles.map((role) => `<span class="role-chip">${escapeHtml(role.role_name)}</span>`).join(" ") : '<span class="muted">未分配</span>'}</td><td>${badge(user.is_active ? "ACTIVE" : "INACTIVE", "status")}</td><td class="muted nowrap">${formatDateTime(user.last_login_at)}</td><td><div class="actions">${iamData.can_manage ? `<button class="btn btn-sm iam-user-edit" data-id="${user.staff_user_id}">编辑</button><button class="btn btn-sm iam-password" data-id="${user.staff_user_id}">重置密码</button>${user.username !== "administer" && user.staff_user_id !== authContext.staff_user_id ? `<button class="btn btn-sm btn-danger iam-user-delete" data-id="${user.staff_user_id}">删除</button>` : ""}` : "—"}</div></td></tr>`).join("")}</tbody></table></div></section>`;
    document.getElementById("iam-user-add")?.addEventListener("click", () => openUserDialog());
    panel.querySelectorAll(".iam-user-edit").forEach((button) => button.addEventListener("click", () => openUserDialog(iamData.users.find((user) => String(user.staff_user_id) === button.dataset.id))));
    panel.querySelectorAll(".iam-password").forEach((button) => button.addEventListener("click", () => openPasswordDialog(iamData.users.find((user) => String(user.staff_user_id) === button.dataset.id))));
    panel.querySelectorAll(".iam-user-delete").forEach((button) => button.addEventListener("click", async () => {
      const user = iamData.users.find((item) => String(item.staff_user_id) === button.dataset.id);
      if (!confirm(`确认删除员工“${user.display_name}”？`)) return;
      try { await api(`/api/iam/users/${user.staff_user_id}`, { method: "DELETE" }); toast("员工账号已删除"); await loadIam(); } catch (error) { toast(error.message, "error"); }
    }));
    return;
  }
  panel.innerHTML = `<div class="page-head compact"><div><h2>角色与操作范围</h2><p>每个员工只能分配一个角色，并按该角色获得操作权限</p></div>${iamData.can_manage ? '<button class="btn btn-primary" id="iam-role-add">新建角色</button>' : ""}</div><div class="role-grid">${iamData.roles.map((role) => `<article class="panel role-card"><div class="role-head"><div><h3>${escapeHtml(role.role_name)}</h3><p>${escapeHtml(role.description || "暂无说明")}</p></div><span class="role-chip">${role.user_count} 人</span></div><div class="permission-chips">${role.permissions.map((permission) => `<span>${escapeHtml(permission.permission_name)}</span>`).join("") || '<span class="muted">未分配权限</span>'}</div><div class="actions role-actions">${iamData.can_manage ? `<button class="btn btn-sm iam-role-edit" data-id="${role.role_id}">编辑权限</button>${role.is_system ? "" : `<button class="btn btn-sm btn-danger iam-role-delete" data-id="${role.role_id}">删除</button>`}` : ""}</div></article>`).join("")}</div>`;
  document.getElementById("iam-role-add")?.addEventListener("click", () => openRoleDialog());
  panel.querySelectorAll(".iam-role-edit").forEach((button) => button.addEventListener("click", () => openRoleDialog(iamData.roles.find((role) => String(role.role_id) === button.dataset.id))));
  panel.querySelectorAll(".iam-role-delete").forEach((button) => button.addEventListener("click", async () => {
    const role = iamData.roles.find((item) => String(item.role_id) === button.dataset.id);
    if (!confirm(`确认删除角色“${role.role_name}”？相关员工将失去该角色权限。`)) return;
    try { await api(`/api/iam/roles/${role.role_id}`, { method: "DELETE" }); toast("角色已删除"); await loadIam(); } catch (error) { toast(error.message, "error"); }
  }));
}

function roleCheckboxes(selectedIds = []) {
  return iamData.roles.map((role) => `<label class="role-option"><input type="radio" name="iam-role" value="${role.role_id}" ${selectedIds.includes(role.role_id) ? "checked" : ""}><span class="role-option-check"></span><span class="role-option-copy"><strong>${escapeHtml(role.role_name)}</strong><small>${escapeHtml(role.description || "可按该角色的权限范围访问系统")}</small></span></label>`).join("");
}

function openUserDialog(user = null) {
  const editing = Boolean(user);
  showDialog(`<div class="dialog-head iam-user-head"><div class="dialog-title-icon">员</div><div class="dialog-title-copy"><h3>${editing ? "编辑员工" : "新建员工"}</h3><p>${editing ? `正在维护账号 ${escapeHtml(user.username)}` : "创建后台账号，并通过角色控制操作范围"}</p></div><button class="dialog-close" data-close-dialog aria-label="关闭">×</button></div>
    <div class="dialog-body iam-user-body">
      <section class="form-section">
        <div class="form-section-head"><span>1</span><div><strong>基本信息</strong><small>${editing ? "调整员工姓名与账号状态" : "用于员工登录和后台身份识别"}</small></div></div>
        <div class="employee-form-grid ${editing ? "editing" : ""}">
          ${editing ? "" : '<div class="field employee-field"><label for="iam-username">登录账号 <em>必填</em></label><input class="input" id="iam-username" maxlength="64" autocomplete="off" placeholder="例如 zhangmin"><small>至少 3 位，支持中英文、数字及 _ . -</small></div>'}
          <div class="field employee-field"><label for="iam-display-name">员工姓名 <em>必填</em></label><input class="input" id="iam-display-name" maxlength="100" value="${escapeHtml(user?.display_name || "")}" placeholder="例如 张敏"><small>用于页面展示和审计记录</small></div>
          ${editing ? `<div class="field employee-field"><label>账号状态</label><label class="account-status-control"><input type="checkbox" id="iam-active" ${user.is_active ? "checked" : ""} ${user.username === "administer" ? "disabled" : ""}><span><strong>允许登录</strong><small>${user.username === "administer" ? "主管理员账号不可停用" : "关闭后现有登录会立即失效"}</small></span></label></div>` : '<div class="field employee-field"><label for="iam-password-new">初始密码 <em>必填</em></label><input class="input" id="iam-password-new" type="password" minlength="6" maxlength="128" autocomplete="new-password" placeholder="输入至少 6 位密码"><small>创建后可随时由管理员重置</small></div>'}
        </div>
      </section>
      <section class="form-section role-section">
        <div class="form-section-head"><span>2</span><div><strong>分配角色</strong><small>只能选择一个角色，员工将获得该角色的操作权限</small></div></div>
        <div class="permission-select-list role-option-grid">${roleCheckboxes(user?.roles.map((role) => role.role_id) || [])}</div>
      </section>
    </div>
    <div class="dialog-foot iam-user-foot"><span>账号创建后即可登录系统</span><div><button class="btn" data-close-dialog>取消</button><button class="btn btn-primary" id="iam-user-save">保存员工</button></div></div>`, "dialog-wide iam-user-dialog");
  document.getElementById("iam-user-save").addEventListener("click", async () => {
    const selectedRole = document.querySelector("[name=iam-role]:checked");
    const display_name = document.getElementById("iam-display-name").value.trim();
    if (!display_name) return toast("请填写员工姓名", "error");
    if (!selectedRole) return toast("请选择一个员工角色", "error");
    const role_id = Number(selectedRole.value);
    const username = editing ? user.username : document.getElementById("iam-username").value.trim();
    const password = editing ? "" : document.getElementById("iam-password-new").value;
    if (!editing && username.length < 3) return toast("登录账号至少需要 3 位", "error");
    if (!editing && password.length < 6) return toast("初始密码至少需要 6 位", "error");
    const payload = editing ? { display_name, is_active: user.username === "administer" ? true : document.getElementById("iam-active").checked, role_id } : { username, display_name, password, role_id };
    try { await api(editing ? `/api/iam/users/${user.staff_user_id}` : "/api/iam/users", { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) }); closeDialog(); toast("员工账号已保存"); await loadIam(); } catch (error) { toast(error.message, "error"); }
  });
}

function openPasswordDialog(user) {
  showDialog(`<div class="dialog-head"><div><h3>重置登录密码</h3><p>${escapeHtml(user.display_name)} · ${escapeHtml(user.username)}</p></div><button class="dialog-close" data-close-dialog>×</button></div><div class="dialog-body"><div class="field"><label for="iam-reset-password">新密码</label><input class="input" id="iam-reset-password" type="password" minlength="6" autocomplete="new-password"><small class="muted">至少 6 位，保存后该账号其他登录会立即失效</small></div></div><div class="dialog-foot"><button class="btn" data-close-dialog>取消</button><button class="btn btn-primary" id="iam-password-save">确认重置</button></div>`);
  document.getElementById("iam-password-save").addEventListener("click", async () => { try { await api(`/api/iam/users/${user.staff_user_id}/reset-password`, { method: "POST", body: JSON.stringify({ password: document.getElementById("iam-reset-password").value }) }); closeDialog(); toast("密码已重置"); if (user.staff_user_id === authContext.staff_user_id) setTimeout(() => location.replace("/login"), 600); } catch (error) { toast(error.message, "error"); } });
}

function permissionCheckboxes(selectedIds = [], locked = false) {
  const modules = { dashboard: "主面板", orders: "订单", reviews: "人工审核", rules: "规则", blacklist: "黑名单", audit: "审计", iam: "权限管理" };
  const grouped = iamData.permissions.reduce((result, item) => { (result[item.module] ||= []).push(item); return result; }, {});
  return Object.entries(grouped).map(([module, items]) => `<section class="permission-module"><strong>${modules[module] || module}</strong><div>${items.map((permission) => `<label class="check permission-check"><input type="checkbox" name="iam-permission" value="${permission.permission_id}" ${selectedIds.includes(permission.permission_id) ? "checked" : ""} ${locked ? "disabled" : ""}><span><b>${escapeHtml(permission.permission_name)}</b><small>${escapeHtml(permission.description || "")}</small></span></label>`).join("")}</div></section>`).join("");
}

function openRoleDialog(role = null) {
  const editing = Boolean(role); const locked = role?.role_code === "ADMINISTRATOR";
  showDialog(`<div class="dialog-head"><div><h3>${editing ? "编辑角色权限" : "新建角色"}</h3><p>${locked ? "超级管理员始终保留全部权限" : "选择该角色允许执行的操作"}</p></div><button class="dialog-close" data-close-dialog>×</button></div><div class="dialog-body"><div class="condition-grid">${editing ? "" : '<div class="field"><label for="iam-role-code">角色编码</label><input class="input" id="iam-role-code" placeholder="如 FINANCE_AUDITOR"></div>'}<div class="field"><label for="iam-role-name">角色名称</label><input class="input" id="iam-role-name" value="${escapeHtml(role?.role_name || "")}"></div></div><div class="field"><label for="iam-role-description">角色说明</label><textarea class="textarea" id="iam-role-description">${escapeHtml(role?.description || "")}</textarea></div><div class="permission-matrix">${permissionCheckboxes(role?.permissions.map((permission) => permission.permission_id) || [], locked)}</div></div><div class="dialog-foot"><button class="btn" data-close-dialog>取消</button><button class="btn btn-primary" id="iam-role-save">保存角色</button></div>`);
  document.getElementById("iam-role-save").addEventListener("click", async () => {
    const permission_ids = [...document.querySelectorAll("[name=iam-permission]:checked")].map((item) => Number(item.value));
    const payload = { role_name: document.getElementById("iam-role-name").value.trim(), description: document.getElementById("iam-role-description").value.trim() || null };
    if (!locked) payload.permission_ids = permission_ids;
    if (!editing) payload.role_code = document.getElementById("iam-role-code").value.trim();
    try { await api(editing ? `/api/iam/roles/${role.role_id}` : "/api/iam/roles", { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) }); closeDialog(); toast("角色权限已保存"); await loadIam(); } catch (error) { toast(error.message, "error"); }
  });
}

async function renderAudit() {
  const root = document.getElementById("page-content");
  root.innerHTML = `<div class="page-head"><div><h2>操作审计</h2><p>规则、名单和审核操作的前后状态留痕</p></div></div><section class="panel"><form class="filters" id="audit-filters"><div class="field filter-field"><label for="audit-action">操作类型</label><select class="select" id="audit-action"><option value="">全部操作</option><option value="RULE_CREATED">创建规则</option><option value="RULE_UPDATED">更新规则</option><option value="RULE_GROUP_UPDATED">更新规则组</option><option value="RISK_RECALCULATED">全量评分重算</option><option value="BLACKLIST_CREATED">新增名单</option><option value="BLACKLIST_UPDATED">更新名单</option><option value="BLACKLIST_DELETED">删除名单</option><option value="REVIEW_DECIDED">审核处置</option></select></div><div class="field"><label>&nbsp;</label><button class="btn btn-primary">筛选</button></div></form><div id="audit-result">${loading()}</div></section>`;
  document.getElementById("audit-filters").addEventListener("submit", (event) => { event.preventDefault(); loadAudit(1); });
  window.loadAudit = loadAudit;
  await loadAudit(1);
}

async function loadAudit(page = 1) {
  const result = document.getElementById("audit-result"); result.innerHTML = loading();
  const params = new URLSearchParams({ page, page_size: 20, sort_by: tableSort.audit.by, sort_order: tableSort.audit.order }); const action = document.getElementById("audit-action").value; if (action) params.set("action", action);
  const data = await api(`/api/audit?${params}`);
  result.innerHTML = data.items.length ? `<div class="table-wrap"><table class="data-table stable-table audit-table"><colgroup>${"<col>".repeat(6)}</colgroup><thead><tr>${sortableHeader("时间", "created_at", tableSort.audit, "desc")}${sortableHeader("操作人", "operator", tableSort.audit)}${sortableHeader("动作", "action", tableSort.audit)}${sortableHeader("对象", "entity_type", tableSort.audit)}${sortableHeader("请求编号", "request_id", tableSort.audit)}<th>变更详情</th></tr></thead><tbody>${data.items.map((item) => `<tr><td class="nowrap muted" title="${formatDateTime(item.created_at)}">${formatDateTime(item.created_at)}</td><td title="${escapeHtml(item.operator)}">${escapeHtml(item.operator)}</td><td class="strong" title="${escapeHtml(item.action)}">${escapeHtml(item.action)}</td><td><span class="mono" title="${escapeHtml(item.entity_type)} #${escapeHtml(item.entity_id)}">${escapeHtml(item.entity_type)} #${escapeHtml(item.entity_id)}</span></td><td class="mono muted" title="${escapeHtml(item.request_id || "—")}">${escapeHtml(item.request_id || "—")}</td><td><details><summary class="link">查看</summary><pre class="json-block">变更前：${escapeHtml(JSON.stringify(item.before_data, null, 2))}\n变更后：${escapeHtml(JSON.stringify(item.after_data, null, 2))}</pre></details></td></tr>`).join("")}</tbody></table></div>${pagination(data, "loadAudit")}` : empty("暂无审计记录");
  bindSortableHeaders(result, tableSort.audit, loadAudit);
}

async function renderAgent() {
  const root = document.getElementById("page-content");
  const data = await api("/api/agent/capabilities");
  const examples = [
    "查看当前风险概览和待审核案件数量",
    "查询最近 10 笔自动拒绝的订单",
    "列出所有启用的规则组和档位分数",
    "查询当前有效的黑护照名单",
  ];
  root.innerHTML = `
    <div class="agent-page">
      <section class="agent-welcome">
        <div class="agent-ai-mark" aria-hidden="true"><span>✦</span></div>
        <div class="agent-welcome-copy"><span>RISK OPERATIONS COPILOT</span><h2>今天要处理什么风险任务？</h2><p>描述需要查询或执行的操作，Agent 会选择对应的业务工具安全处理。</p></div>
        <div class="agent-connection"><i></i><div><strong>数据库工具已连接</strong><span>仅限系统管理员</span></div></div>
      </section>
      <section class="agent-workspace-grid">
        <article class="agent-main-card">
          <div class="agent-card-head"><div><span class="agent-section-icon">01</span><div><strong>创建任务</strong><small>订单号、案件号和操作条件请在本次输入中一次说明</small></div></div><span class="agent-private-badge"><i></i>不保存历史</span></div>
          <form id="agent-form">
            <label class="agent-composer" for="agent-message"><span class="agent-composer-star" aria-hidden="true">✦</span><textarea id="agent-message" maxlength="200" placeholder="例如：查询风险分 75 分以上的最近 10 笔订单，并总结主要命中规则"></textarea><span class="agent-char-count" id="agent-count">0 / 200</span></label>
            <div class="agent-form-foot"><span class="agent-audit-note"><i>✓</i>数据库变更会自动写入审计日志</span><button class="agent-submit" id="agent-submit" type="submit"><span>开始执行</span><b>→</b></button></div>
          </form>
          <div class="agent-examples"><div class="agent-examples-title"><span>常用任务</span><small>点击即可填入</small></div><div>${examples.map((item, index) => `<button type="button" data-agent-example="${escapeHtml(item)}"><i>${["◫", "⌁", "⚙", "⊘"][index]}</i><span>${escapeHtml(item)}</span><b>↗</b></button>`).join("")}</div></div>
          <div class="agent-result-section"><div class="agent-result-label"><span class="agent-section-icon">02</span><div><strong>执行结果</strong><small>新任务会替换当前结果</small></div></div><div id="agent-result" class="agent-result is-empty"><div class="agent-result-placeholder"><span>✦</span><strong>结果将在这里显示</strong><p>Agent 尚未执行任务</p></div></div></div>
        </article>
        <aside class="agent-side-stack">
          <section class="agent-side-card"><div class="agent-side-title"><span>可用能力</span><small>${data.capabilities.length} 项工具范围</small></div><div class="agent-capabilities">${data.capabilities.map((item, index) => `<div><b>${String(index + 1).padStart(2, "0")}</b><span>${escapeHtml(item)}</span></div>`).join("")}</div></section>
          <section class="agent-security-card"><div class="agent-shield">✓</div><div><strong>受控操作环境</strong><p>仅调用经过授权的业务工具，无法执行任意 SQL。</p><ul><li>不处理项目外问题</li><li>不保存聊天历史</li><li>敏感证件号脱敏展示</li></ul></div></section>
        </aside>
      </section>
    </div>`;

  const form = document.getElementById("agent-form");
  const input = document.getElementById("agent-message");
  const counter = document.getElementById("agent-count");
  const result = document.getElementById("agent-result");
  const submit = document.getElementById("agent-submit");
  input.addEventListener("input", () => { counter.textContent = `${input.value.length} / 200`; });
  document.querySelectorAll("[data-agent-example]").forEach((button) => button.addEventListener("click", () => {
    input.value = button.dataset.agentExample;
    input.dispatchEvent(new Event("input"));
    input.focus();
  }));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return toast("请输入需要 Agent 执行的任务", "error");
    submit.disabled = true;
    result.className = "agent-result is-loading";
    result.innerHTML = `<div class="agent-thinking"><div class="agent-pulse"><i></i><i></i><i></i></div><div><strong>正在分析任务并调用数据库工具</strong><span>复杂的全量评分重算可能需要更长时间</span></div></div>`;
    try {
      const response = await api("/api/agent/run", { method: "POST", body: JSON.stringify({ message }) });
      const toolNames = response.tools.map((tool) => tool.name);
      result.className = "agent-result";
      result.innerHTML = `<div class="agent-result-head"><div><span>本次执行结果</span><small>${escapeHtml(response.model)}</small></div>${toolNames.length ? `<div class="agent-tool-count">调用 ${toolNames.length} 个工具</div>` : ""}</div><div class="agent-answer">${renderAgentAnswer(response.answer || "任务已完成，但模型没有返回文字说明。")}</div>${toolNames.length ? `<div class="agent-tool-trace"><span>工具记录</span><div>${response.tools.map((tool) => `<i class="${tool.status === "success" ? "success" : "error"}">${escapeHtml(tool.name)}</i>`).join("")}</div></div>` : ""}`;
    } catch (error) {
      result.className = "agent-result is-error";
      result.innerHTML = `<div class="agent-error"><span>!</span><div><strong>任务执行失败</strong><p>${escapeHtml(error.message)}</p></div></div>`;
    } finally {
      submit.disabled = false;
    }
  });
}

async function bootstrap() {
  authContext = await api("/api/auth/me");
  mountShell();
  const renderers = { dashboard: renderDashboard, orders: renderOrders, orderDetail: renderOrderDetail, reviews: renderReviews, rules: renderRules, blacklist: renderBlacklist, audit: renderAudit, permissions: renderPermissions, agent: renderAgent };
  await (renderers[currentPage] || renderDashboard)();
}

bootstrap().catch((error) => {
  if (document.getElementById("page-content")) fatal(error);
});
