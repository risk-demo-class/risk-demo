(() => {
  const page = document.body.dataset.page;
  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
  const number = new Intl.NumberFormat("zh-CN", {maximumFractionDigits: 2});
  const money = new Intl.NumberFormat("zh-CN", {style: "currency", currency: "USD", maximumFractionDigits: 0});
  const dateTime = (value) => value ? new Date(value).toLocaleString("zh-CN", {month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit"}) : "-";

  async function api(path, options = {}) {
    const response = await fetch(path, {headers: {"Content-Type": "application/json"}, ...options});
    if (!response.ok) {
      let detail = `请求失败 (${response.status})`;
      try { detail = (await response.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    return response.json();
  }

  function toast(message) {
    const node = qs("#app-toast");
    qs(".toast-body", node).textContent = message;
    bootstrap.Toast.getOrCreateInstance(node).show();
  }

  function errorState(message) {
    return `<div class="error-state"><strong>数据加载失败</strong><span>${esc(message)}，请检查 MySQL 与服务配置。</span></div>`;
  }

  async function loadHealth() {
    const health = qs("#system-health");
    try {
      const data = await api("/api/health");
      health.className = "system-health ok";
      health.innerHTML = `<i class="ph ph-check-circle"></i><span>数据库正常，模型${data.model_loaded ? "已加载" : "待训练"}</span>`;
    } catch (error) {
      health.className = "system-health error";
      health.innerHTML = `<i class="ph ph-warning-circle"></i><span>${esc(error.message)}</span>`;
    }
  }

  function statusBadge(value) {
    const labels = {APPROVED:"通过", DECLINED:"补充材料", REJECTED:"拒绝", REFUNDED:"退款", PROCESSING:"处理中", INVESTIGATING:"调查中", CLOSED:"已关闭", PENDING:"待处理"};
    return `<span class="status-badge ${String(value).toLowerCase()}">${labels[value] || esc(value)}</span>`;
  }

  async function initDashboard() {
    let transactions = [];
    const body = qs("#transaction-body");
    try {
      const [stats, trend, cases, inbounds] = await Promise.all([
        api("/api/dashboard/stats"), api("/api/dashboard/trend"), api("/api/cases?limit=5"), api("/api/inbounds?limit=40")
      ]);
      const metrics = [
        ["入账总额", money.format(stats.inbound_amount_usd || 0), `${number.format(stats.inbound_count)} 笔`],
        ["高风险结果", `${number.format(stats.high_risk_rate || 0)}%`, `${number.format(stats.high_risk_count)} 笔拒绝或退款`, true],
        ["活跃商户", number.format(stats.active_customers), `${number.format(stats.distinct_payers)} 个付款人`],
        ["待处理案件", number.format(stats.open_cases || 0), `${number.format(stats.urgent_cases || 0)} 个 P0/P1`],
        ["快速出款", number.format(stats.rapid_payouts || 0), "入账后 1 小时内"],
        ["模型验证", stats.model?.val_auc ? stats.model.val_auc.toFixed(3) : "待训练", stats.model?.val_f1 ? `F1 ${stats.model.val_f1.toFixed(3)}` : "暂无指标"]
      ];
      qs("#metric-strip").innerHTML = metrics.map(([label, value, note, risk]) => `<div class="metric"><span>${label}</span><strong class="${risk ? "risk-value" : ""}">${value}</strong><small>${note}</small></div>`).join("");

      const chartNode = qs("#risk-trend");
      qs("#trend-wrap").classList.remove("loading-surface");
      new Chart(chartNode, {
        type: "line",
        data: {labels: trend.map(item => item.day.slice(5)), datasets: [
          {label:"高风险", data: trend.map(item => item.high_risk), borderColor:"#a33a36", backgroundColor:"rgba(163,58,54,.08)", pointRadius:2, tension:.22, yAxisID:"risk"},
          {label:"金额", data: trend.map(item => Number(item.amount_usd)), borderColor:"#0b7465", pointRadius:0, tension:.22, yAxisID:"amount"}
        ]},
        options: {responsive:true, maintainAspectRatio:false, animation:{duration:180}, interaction:{mode:"index", intersect:false}, plugins:{legend:{display:false}}, scales:{x:{grid:{display:false}, ticks:{maxTicksLimit:8, color:"#6b7874"}}, risk:{position:"left", beginAtZero:true, grid:{color:"#e4e9e7"}, ticks:{precision:0, color:"#6b7874"}}, amount:{position:"right", grid:{display:false}, ticks:{callback:(v)=>`${Math.round(v/1000)}k`, color:"#6b7874"}}}}
      });

      qs("#case-preview").classList.remove("loading-surface");
      qs("#case-preview").innerHTML = cases.length ? cases.map(item => `<div class="compact-case"><span class="priority ${item.priority.toLowerCase()}">${esc(item.priority)}</span><div><h3>${esc(item.title)}</h3><p>${esc(item.customer_name || "未知商户")}，${esc(item.case_type)}，${dateTime(item.opened_at)}</p></div></div>`).join("") : `<div class="empty-state"><i class="ph ph-check-circle"></i><h3>暂无待处理案件</h3><p>新的人工审核任务会出现在这里。</p></div>`;
      transactions = inbounds;
      renderTransactions(transactions);
    } catch (error) {
      qs("#metric-strip").innerHTML = errorState(error.message);
      qs("#case-preview").innerHTML = errorState(error.message);
      body.innerHTML = `<tr><td colspan="7">${errorState(error.message)}</td></tr>`;
    }

    function renderTransactions(items) {
      qs("#transaction-empty").classList.toggle("d-none", items.length > 0);
      body.innerHTML = items.map(item => `<tr>
        <td><span class="primary-cell mono">${esc(item.transaction_id)}</span><span class="secondary-cell">${dateTime(item.received_at)}</span></td>
        <td><span class="primary-cell">${esc(item.customer_name)}</span><span class="secondary-cell mono">${esc(item.client_id)}</span></td>
        <td><span class="primary-cell">${esc(item.payer_name)}</span><span class="secondary-cell">${item.external_risk_label ? esc(item.external_risk_label) : "无外部风险标签"}</span></td>
        <td class="mono">${money.format(Number(item.amount_usd))}<span class="secondary-cell">原币 ${esc(item.currency)}</span></td>
        <td><span class="primary-cell">${esc(item.origin_country)} → VA</span><span class="secondary-cell">${esc(item.business_type)}</span></td>
        <td>${statusBadge(item.inbound_status)}</td>
        <td class="text-end"><button class="btn-table assess-btn" data-id="${item.id}"><i class="ph ph-scan"></i>评估并留痕</button></td>
      </tr>`).join("");
      qsa(".assess-btn", body).forEach(button => button.addEventListener("click", () => assess(Number(button.dataset.id), button)));
    }

    qs("#transaction-search").addEventListener("input", (event) => {
      const term = event.target.value.trim().toLowerCase();
      renderTransactions(transactions.filter(item => `${item.transaction_id} ${item.customer_name} ${item.client_id}`.toLowerCase().includes(term)));
    });
    qs("#refresh-dashboard").addEventListener("click", () => window.location.reload());
  }

  async function assess(id, button) {
    const drawerNode = qs("#evidenceDrawer");
    const drawer = bootstrap.Offcanvas.getOrCreateInstance(drawerNode);
    const content = qs("#evidence-body");
    button.disabled = true;
    content.innerHTML = `<div class="drawer-skeleton"><span></span><span></span><span></span></div>`;
    drawer.show();
    try {
      const result = await api("/api/risk/check", {method:"POST", body:JSON.stringify({inbound_payment_id:id, persist:true})});
      qs("#evidence-subtitle").textContent = `${result.transaction_id}，决策已写入审计表`;
      const decisionLabels = {ALLOW:"通过", FLAG:"标记", MANUAL_REVIEW:"人工审核", REJECT:"拒绝"};
      const important = ["amount_usd","expected_volume_ratio","payer_risk_score","order_risk_score","is_third_party_payment","is_first_payer","duplicate_doc_hash_count","max_doc_tamper_score","prior_inbound_count_24h","payer_prior_customer_count"];
      content.innerHTML = `
        <div class="decision-banner ${result.decision.toLowerCase()}"><span>联合决策</span><strong>${decisionLabels[result.decision]}</strong></div>
        <div class="drawer-score"><div><span>最终分</span><strong>${result.final_score.toFixed(1)}</strong></div><div><span>规则分</span><strong>${result.rule_score}</strong></div><div><span>模型概率</span><strong>${(result.ml_probability * 100).toFixed(1)}%</strong></div></div>
        <section class="drawer-section"><h3>命中规则 (${result.rule_hits.length})</h3>${result.rule_hits.length ? result.rule_hits.map(hit => `<article class="rule-hit"><div class="rule-hit-head"><h4>${esc(hit.id)} ${esc(hit.name)}</h4><span class="severity-badge ${hit.severity.toLowerCase()}">${hit.score}</span></div><p>${esc(hit.fraud_scenario)}</p></article>`).join("") : `<div class="empty-state"><i class="ph ph-shield-check"></i><h3>未命中业务规则</h3><p>本次结论主要由模型和低风险事实构成。</p></div>`}</section>
        <section class="drawer-section"><h3>关键特征</h3><dl class="feature-kv">${important.map(key => `<dt>${esc(key)}</dt><dd>${number.format(Number(result.features[key] || 0))}</dd>`).join("")}</dl></section>
        <section class="drawer-section"><h3>审计标识</h3><dl class="feature-kv"><dt>risk_event</dt><dd>${esc(result.risk_event_id)}</dd><dt>risk_decision</dt><dd>${esc(result.risk_decision_id)}</dd></dl></section>`;
      toast("风险评估已完成并写入 MySQL");
    } catch (error) {
      content.innerHTML = errorState(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function initRules() {
    const body = qs("#rule-body");
    let rules = [];
    try {
      rules = await api("/api/rules");
      const stages = [...new Set(rules.map(rule => rule.stage))];
      qs("#stage-filter").insertAdjacentHTML("beforeend", stages.map(stage => `<option>${esc(stage)}</option>`).join(""));
      render();
    } catch (error) { body.innerHTML = `<tr><td colspan="7">${errorState(error.message)}</td></tr>`; }
    function render() {
      const term = qs("#rule-search").value.trim().toLowerCase();
      const stage = qs("#stage-filter").value;
      const severity = qs("#severity-filter").value;
      const filtered = rules.filter(rule => (!term || `${rule.id} ${rule.name} ${rule.fraud_scenario}`.toLowerCase().includes(term)) && (!stage || rule.stage === stage) && (!severity || rule.severity === severity));
      qs("#rule-count").textContent = filtered.length;
      qs("#rule-empty").classList.toggle("d-none", filtered.length > 0);
      body.innerHTML = filtered.map(rule => `<tr><td><span class="primary-cell mono">${esc(rule.id)}</span><span class="secondary-cell">${esc(rule.name)}</span></td><td><span class="stage-badge">${esc(rule.stage)}</span></td><td><span class="primary-cell">${esc(rule.category)}</span><span class="severity-badge ${rule.severity.toLowerCase()}">${esc(rule.severity)}</span></td><td>${esc(rule.fraud_scenario)}</td><td class="mono">${rule.score}${rule.veto ? `<span class="secondary-cell">一票否决</span>` : ""}</td><td><span class="action-badge ${rule.action.toLowerCase()}">${esc(rule.action)}</span></td><td><code class="condition-code" title="${esc(JSON.stringify(rule.condition))}">${esc(JSON.stringify(rule.condition))}</code></td></tr>`).join("");
    }
    ["#rule-search", "#stage-filter", "#severity-filter"].forEach(selector => qs(selector).addEventListener("input", render));
  }

  async function initCases() {
    const body = qs("#case-body");
    try {
      const cases = await api("/api/cases?limit=100");
      qs("#case-empty").classList.toggle("d-none", cases.length > 0);
      body.innerHTML = cases.map(item => `<tr><td><span class="primary-cell mono">${esc(item.case_id)}</span><span class="secondary-cell">${esc(item.title)}</span></td><td><span class="priority ${item.priority.toLowerCase()}">${esc(item.priority)}</span></td><td>${esc(item.case_type)}</td><td><span class="primary-cell">${esc(item.customer_name || "未知商户")}</span><span class="secondary-cell mono">${esc(item.client_id || "-")}</span></td><td>${statusBadge(item.status)}</td><td>${esc(item.assignee || "待分配")}</td><td class="mono">${dateTime(item.due_at)}</td></tr>`).join("");
    } catch (error) { body.innerHTML = `<tr><td colspan="7">${errorState(error.message)}</td></tr>`; }
  }

  async function initModel() {
    try {
      const data = await api("/api/model/metrics");
      const metrics = [
        ["验证 AUC", data.val_auc.toFixed(3), "排序能力"],
        ["验证 F1", data.val_f1.toFixed(3), "精确率与召回率平衡"],
        ["决策阈值", data.threshold.toFixed(3), "由校准集选择"],
        ["正例比例", `${(data.positive_rate*100).toFixed(1)}%`, `${data.dataset_rows} 条标签样本`],
        ["特征数量", data.feature_count, "仅使用审核时点可得字段"]
      ];
      qs("#model-metrics").innerHTML = metrics.map(([label,value,note]) => `<div class="metric"><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`).join("");
      const cm = data.confusion_matrix;
      qs("#confusion-matrix").classList.remove("loading-surface");
      qs("#confusion-matrix").innerHTML = `<div></div><div class="axis">预测正常</div><div class="axis">预测风险</div><div class="axis">实际正常</div><div class="cell good"><strong>${cm.tn}</strong><span>正确放行</span></div><div class="cell bad"><strong>${cm.fp}</strong><span>误报</span></div><div class="axis">实际风险</div><div class="cell bad"><strong>${cm.fn}</strong><span>漏报</span></div><div class="cell good"><strong>${cm.tp}</strong><span>正确识别</span></div>`;
      qs("#split-detail").classList.remove("loading-surface");
      qs("#split-detail").innerHTML = `<div><dt>训练集</dt><dd>${data.train_rows}</dd></div><div><dt>阈值校准集</dt><dd>${data.calibration_rows}</dd></div><div><dt>时间验证集</dt><dd>${data.validation_rows}</dd></div><div><dt>验证窗口</dt><dd>${esc(data.validation_window.from.slice(0,10))} 至 ${esc(data.validation_window.to.slice(0,10))}</dd></div><div><dt>验证精确率</dt><dd>${data.val_precision.toFixed(3)}</dd></div><div><dt>验证召回率</dt><dd>${data.val_recall.toFixed(3)}</dd></div>`;
      const max = Math.max(...data.top_features.map(item => item.importance));
      qs("#feature-importance").classList.remove("loading-surface");
      qs("#feature-importance").innerHTML = data.top_features.map(item => `<div class="feature-row"><span class="name" title="${esc(item.name)}">${esc(item.name)}</span><span class="importance-line"><span style="width:${(item.importance/max*100).toFixed(1)}%"></span></span><span class="value">${item.importance.toFixed(4)}</span></div>`).join("");
    } catch (error) {
      qs("#model-metrics").innerHTML = errorState(error.message);
      qs("#confusion-matrix").innerHTML = errorState(error.message);
      qs("#split-detail").innerHTML = errorState(error.message);
      qs("#feature-importance").innerHTML = errorState(error.message);
    }
  }

  async function initRiskCheck() {
    const form = qs("#risk-check-form");
    const eventType = qs("#risk-event-type");
    const businessId = qs("#risk-business-id");
    const options = qs("#risk-subject-options");
    const body = qs("#risk-subject-body");
    const head = qs("#risk-subject-head");
    const resultNode = qs("#risk-check-result");
    const submit = qs("#run-risk-check");
    let inbounds = [];
    let payouts = [];

    try {
      [inbounds, payouts] = await Promise.all([api("/api/inbounds?limit=30"), api("/api/payouts?limit=30")]);
      renderSubjects();
    } catch (error) {
      body.innerHTML = `<tr><td>${errorState(error.message)}</td></tr>`;
    }

    function renderSubjects() {
      const inbound = eventType.value === "INBOUND";
      const items = inbound ? inbounds : payouts;
      qs("#risk-id-help").textContent = inbound ? "支持入账 transaction_id 或内部数字 ID" : "支持出款 payout_id 或内部数字 ID";
      businessId.placeholder = inbound ? "例如 IN_00000726" : "例如 PO_00000450";
      options.innerHTML = items.map(item => `<option value="${esc(inbound ? item.transaction_id : item.payout_id)}">${esc(item.customer_name)}</option>`).join("");
      qs("#risk-subject-count").textContent = `${items.length} 条最近${inbound ? "入账" : "出款"}`;
      head.innerHTML = inbound
        ? `<tr><th>入账</th><th>商户</th><th>付款人</th><th>金额</th><th>结果</th></tr>`
        : `<tr><th>出款</th><th>商户</th><th>受益人</th><th>金额</th><th>状态</th></tr>`;
      body.innerHTML = items.map(item => inbound ? `<tr>
        <td><button type="button" class="subject-select" data-id="${esc(item.transaction_id)}"><span class="primary-cell mono">${esc(item.transaction_id)}</span><span class="secondary-cell">${dateTime(item.received_at)}</span></button></td>
        <td><span class="primary-cell">${esc(item.customer_name)}</span><span class="secondary-cell mono">${esc(item.client_id)}</span></td>
        <td>${esc(item.payer_name)}</td><td class="mono">${money.format(Number(item.amount_usd))}</td><td>${statusBadge(item.inbound_status)}</td>
      </tr>` : `<tr>
        <td><button type="button" class="subject-select" data-id="${esc(item.payout_id)}"><span class="primary-cell mono">${esc(item.payout_id)}</span><span class="secondary-cell">${dateTime(item.requested_at)}</span></button></td>
        <td><span class="primary-cell">${esc(item.customer_name)}</span><span class="secondary-cell mono">${esc(item.client_id)}</span></td>
        <td><span class="primary-cell">${esc(item.beneficiary_name)}</span><span class="secondary-cell mono">${esc(item.beneficiary_account_ref)}</span></td>
        <td class="mono">${number.format(Number(item.pay_amount))} ${esc(item.pay_currency)}</td><td>${statusBadge(item.status)}</td>
      </tr>`).join("");
      qsa(".subject-select", body).forEach(button => button.addEventListener("click", () => {
        businessId.value = button.dataset.id;
        businessId.focus();
      }));
    }

    function renderRiskResult(result) {
      const labels = {ALLOW:"通过", FLAG:"标记", MANUAL_REVIEW:"人工审核", REJECT:"拒绝"};
      const importantKeys = result.event_type === "INBOUND"
        ? ["amount_usd", "payer_risk_score", "is_third_party_payment", "duplicate_doc_hash_count", "prior_inbound_count_24h", "payer_prior_customer_count"]
        : ["pay_amount_usd", "seconds_since_inbound", "is_new_beneficiary", "recent_security_event_flag", "balance_drain_ratio", "beneficiary_customer_count"];
      const blacklistHtml = result.blacklist_hits.length ? result.blacklist_hits.map(hit => `<div class="blacklist-hit"><strong>${esc(hit.entity_type)} 黑名单命中</strong><span>${esc(hit.entity_value)} / ${esc(hit.reason_code)} / ${esc(hit.severity)}</span></div>`).join("") : "";
      const rulesHtml = result.rule_hits.length ? result.rule_hits.map(hit => `<article class="rule-hit"><div class="rule-hit-head"><h4>${esc(hit.id)} ${esc(hit.name)}</h4><span class="severity-badge ${hit.severity.toLowerCase()}">${hit.score}</span></div><p>${esc(hit.fraud_scenario)}</p></article>`).join("") : `<div class="empty-state"><i class="ph ph-shield-check"></i><h3>未命中业务规则</h3><p>本次未发现明确规则红线。</p></div>`;
      resultNode.innerHTML = `<div class="result-ledger">
        <div class="result-verdict ${result.decision.toLowerCase()}"><div><span>${esc(result.event_type)} 联合决策</span><strong>${labels[result.decision] || esc(result.decision)}</strong><small>${result.blacklist_match ? "黑名单一票否决" : (result.veto ? "业务红线一票否决" : "规则与模型联合评估")}</small></div><div class="result-score">${Number(result.final_score).toFixed(1)}</div></div>
        <div class="result-score-grid"><div><span>业务号</span><strong>${esc(result.business_id)}</strong></div><div><span>规则分</span><strong>${Number(result.rule_score || 0).toFixed(0)}</strong></div><div><span>模型概率</span><strong>${result.model_loaded ? `${(Number(result.ml_probability) * 100).toFixed(1)}%` : "未参与"}</strong></div></div>
        <div class="result-evidence"><section><h3>决策证据</h3>${blacklistHtml}${rulesHtml}</section><section><h3>关键特征</h3><dl class="feature-kv">${importantKeys.map(key => `<dt>${esc(key)}</dt><dd>${number.format(Number(result.features[key] || 0))}</dd>`).join("")}</dl>${result.risk_event_id ? `<div class="drawer-section"><h3>审计标识</h3><dl class="feature-kv"><dt>risk_event</dt><dd>${esc(result.risk_event_id)}</dd><dt>risk_decision</dt><dd>${esc(result.risk_decision_id)}</dd></dl></div>` : ""}</section></div>
      </div>`;
    }

    eventType.addEventListener("change", () => {
      businessId.value = "";
      renderSubjects();
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      submit.innerHTML = `<i class="ph ph-circle-notch"></i>正在联合评估`;
      resultNode.innerHTML = `<div class="result-loading"><span></span><span></span><span></span></div>`;
      try {
        const result = await api("/api/risk/check-workbench", {method:"POST", body:JSON.stringify({event_type:eventType.value, business_id:businessId.value.trim(), persist:qs("#risk-persist").checked})});
        renderRiskResult(result);
        toast(result.blacklist_match ? "命中黑名单，已执行一票否决" : "风险检查已完成");
      } catch (error) {
        resultNode.innerHTML = errorState(error.message);
      } finally {
        submit.disabled = false;
        submit.innerHTML = `<i class="ph ph-magnifying-glass"></i>执行检查`;
      }
    });
  }

  function formatAssistantReply(value) {
    const lines = esc(value).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").split("\n");
    let html = "";
    let listType = null;
    const closeList = () => {
      if (listType) html += `</${listType}>`;
      listType = null;
    };
    lines.forEach(line => {
      const heading = line.match(/^#{1,3}\s+(.+)/);
      const ordered = line.match(/^\d+\.\s+(.+)/);
      if (heading) {
        closeList();
        html += `<h3>${heading[1]}</h3>`;
      } else if (line.startsWith("- ")) {
        if (listType !== "ul") { closeList(); html += "<ul>"; listType = "ul"; }
        html += `<li>${line.slice(2)}</li>`;
      } else if (ordered) {
        if (listType !== "ol") { closeList(); html += "<ol>"; listType = "ol"; }
        html += `<li>${ordered[1]}</li>`;
      } else {
        closeList();
        if (line.trim()) html += `<p>${line}</p>`;
      }
    });
    closeList();
    return html;
  }

  async function initAssistant() {
    const form = qs("#assistant-form");
    const input = qs("#assistant-input");
    const messages = qs("#chat-messages");
    const send = qs("#send-assistant");
    let sessionId = null;
    let assistantProvider = "本地分析";
    try {
      const status = await api("/api/agent/status");
      const mode = qs("#assistant-mode");
      mode.className = "system-health ok";
      assistantProvider = status.configured ? "DeepSeek" : "本地分析";
      mode.innerHTML = `<i class="ph ph-cpu"></i><span>${status.configured ? `${esc(status.model)} 已连接` : "本地分析回退"}</span>`;
    } catch (_) {}

    function addMessage(role, content, loading = false) {
      const article = document.createElement("article");
      article.className = `chat-message ${role === "user" ? "user-message" : "assistant-message"}${loading ? " chat-loading" : ""}`;
      article.innerHTML = role === "user"
        ? `<div><strong>你</strong><div class="message-content"><p>${esc(content)}</p></div></div><div class="message-avatar"><i class="ph ph-user"></i></div>`
        : `<div class="message-avatar"><i class="ph ph-robot"></i></div><div><strong>DeepSeek Risk Copilot</strong><div class="message-content">${loading ? `<p><span>正在聚合本地证据并请求${assistantProvider}总结</span></p>` : formatAssistantReply(content)}</div></div>`;
      messages.appendChild(article);
      messages.scrollTop = messages.scrollHeight;
      return article;
    }

    async function sendMessage(message) {
      const clean = message.trim();
      if (!clean) return;
      addMessage("user", clean);
      const loading = addMessage("assistant", "", true);
      send.disabled = true;
      input.disabled = true;
      try {
        const result = await api("/api/agent/chat", {method:"POST", body:JSON.stringify({message:clean, session_id:sessionId})});
        sessionId = result.session_id;
        const modeLabel = result.mode === "DEEPSEEK" ? `DeepSeek / ${result.model}` : (result.fallback_reason ? "本地回退" : "本地分析");
        qs("#assistant-session-label").textContent = `${modeLabel} / ${sessionId}`;
        loading.classList.remove("chat-loading");
        qs(".message-content", loading).innerHTML = formatAssistantReply(result.reply);
      } catch (error) {
        loading.classList.remove("chat-loading");
        qs(".message-content", loading).innerHTML = `<p>${esc(error.message)}</p>`;
      } finally {
        send.disabled = false;
        input.disabled = false;
        input.value = "";
        input.focus();
      }
    }

    form.addEventListener("submit", (event) => { event.preventDefault(); sendMessage(input.value); });
    qsa("[data-prompt]", qs("#assistant-prompts")).forEach(button => button.addEventListener("click", () => sendMessage(button.dataset.prompt)));
    qs("#clear-assistant").addEventListener("click", async () => {
      if (sessionId) await api("/api/agent/clear", {method:"POST", body:JSON.stringify({session_id:sessionId})});
      sessionId = null;
      messages.innerHTML = `<article class="chat-message assistant-message"><div class="message-avatar"><i class="ph ph-robot"></i></div><div><strong>DeepSeek Risk Copilot</strong><div class="message-content"><p>会话已清空。可以开始新的风险查询。</p></div></div></article>`;
      qs("#assistant-session-label").textContent = "新会话";
    });
  }

  async function initBlacklist() {
    const body = qs("#blacklist-body");
    const form = qs("#blacklist-form");
    const save = qs("#save-blacklist");
    let debounce = null;

    async function load() {
      const params = new URLSearchParams({page:"1", page_size:"100", status:qs("#blacklist-filter-status").value});
      const type = qs("#blacklist-filter-type").value;
      const term = qs("#blacklist-search").value.trim();
      if (type) params.set("entity_type", type);
      if (term) params.set("q", term);
      body.innerHTML = `<tr><td colspan="8"><div class="table-skeleton"><span></span><span></span><span></span></div></td></tr>`;
      try {
        const data = await api(`/api/blacklist?${params}`);
        qs("#blacklist-summary").innerHTML = `<span><strong>${data.total}</strong> 条名单记录，黑名单命中在规则与模型之前执行一票否决。</span>`;
        qs("#blacklist-empty").classList.toggle("d-none", data.items.length > 0);
        body.innerHTML = data.items.map(item => `<tr>
          <td><span class="primary-cell">${esc(item.display_name || item.entity_type)}</span><span class="secondary-cell">${esc(item.entity_type)}</span></td>
          <td class="mono">${esc(item.entity_value)}</td>
          <td><span class="primary-cell">${esc(item.reason_code)}</span><span class="secondary-cell">${esc(item.reason_detail || "无补充说明")}</span></td>
          <td><span class="severity-badge ${item.severity.toLowerCase()}">${esc(item.severity)}</span></td>
          <td>${esc(item.source)}<span class="secondary-cell">${esc(item.created_by)}</span></td>
          <td class="mono">${number.format(item.hit_count)}<span class="secondary-cell">${item.last_hit_at ? dateTime(item.last_hit_at) : "尚未命中"}</span></td>
          <td><span class="status-badge ${item.status.toLowerCase()}">${{ACTIVE:"有效",EXPIRED:"已过期",REMOVED:"已移除"}[item.status]}</span>${item.expires_at ? `<span class="secondary-cell">至 ${dateTime(item.expires_at)}</span>` : ""}</td>
          <td class="text-end">${item.status === "ACTIVE" ? `<button class="btn-table remove-blacklist" data-id="${item.id}" data-value="${esc(item.entity_value)}"><i class="ph ph-x"></i>移除</button>` : ""}</td>
        </tr>`).join("");
        qsa(".remove-blacklist", body).forEach(button => button.addEventListener("click", async () => {
          if (!window.confirm(`确认移除黑名单 ${button.dataset.value}？`)) return;
          button.disabled = true;
          try {
            await api(`/api/blacklist/${button.dataset.id}`, {method:"DELETE", body:JSON.stringify({removed_by:"risk-operator", removed_reason:"前端人工移除"})});
            toast("黑名单已软删除并保留审计字段");
            load();
          } catch (error) { toast(error.message); button.disabled = false; }
        }));
      } catch (error) {
        body.innerHTML = `<tr><td colspan="8">${errorState(error.message)}</td></tr>`;
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      save.disabled = true;
      save.innerHTML = `<i class="ph ph-circle-notch"></i>正在写入 MySQL`;
      const expiry = qs("#blacklist-expiry").value;
      const payload = {
        entity_type:qs("#blacklist-type").value,
        entity_value:qs("#blacklist-value").value.trim(),
        display_name:qs("#blacklist-name").value.trim() || null,
        reason_code:qs("#blacklist-reason").value,
        reason_detail:qs("#blacklist-detail").value.trim() || null,
        severity:qs("#blacklist-severity").value,
        source:"MANUAL",
        source_refs:["risk-operator-ui"],
        expires_at:expiry ? new Date(expiry).toISOString() : null,
        created_by:"risk-operator"
      };
      try {
        await api("/api/blacklist", {method:"POST", body:JSON.stringify(payload)});
        form.reset();
        toast("黑名单已写入 MySQL 并立即生效");
        await load();
      } catch (error) { toast(error.message); }
      finally { save.disabled = false; save.innerHTML = `<i class="ph ph-plus"></i>写入黑名单`; }
    });
    ["#blacklist-filter-type", "#blacklist-filter-status"].forEach(selector => qs(selector).addEventListener("change", load));
    qs("#blacklist-search").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(load, 220); });
    load();
  }

  loadHealth();
  if (page === "dashboard") initDashboard();
  if (page === "rules") initRules();
  if (page === "cases") initCases();
  if (page === "model") initModel();
  if (page === "risk-check") initRiskCheck();
  if (page === "assistant") initAssistant();
  if (page === "blacklist") initBlacklist();
})();
