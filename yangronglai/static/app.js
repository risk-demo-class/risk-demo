function updateClock() {
  const node = document.getElementById("live-clock");
  if (node) node.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

async function submitRiskCheck(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const result = document.getElementById("risk-result");
  const data = new FormData(form);
  let eventData;
  try {
    eventData = JSON.parse(data.get("event_data") || "{}");
  } catch (error) {
    result.textContent = `event_data 不是合法 JSON：${error.message}`;
    return;
  }

  result.textContent = "正在计算特征并执行规则……";
  const requestStatus = document.getElementById("request-status");
  if (requestStatus) {
    requestStatus.textContent = "执行中";
    requestStatus.className = "component-state";
  }
  try {
    const response = await fetch("/api/risk/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario: data.get("scenario"),
        source_id: data.get("source_id"),
        user_id: data.get("user_id"),
        event_data: eventData,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    if (requestStatus) {
      requestStatus.textContent = `执行成功 · ${payload.decision}`;
      requestStatus.className = "component-state on";
    }
    const appealCta = document.getElementById("appeal-cta");
    if (payload.appeal?.allowed) {
      window.sessionStorage.setItem("bankrisk_appeal_context", JSON.stringify({
        assessment_id: payload.assessment_id,
        appeal_token: payload.appeal.token,
        deadline: payload.appeal.deadline,
      }));
      if (appealCta) {
        appealCta.href = payload.appeal.page_url || "/appeal";
        appealCta.hidden = false;
      }
    } else {
      window.sessionStorage.removeItem("bankrisk_appeal_context");
      if (appealCta) appealCta.hidden = true;
    }
    result.textContent = `系统执行成功\n风控决策：${payload.decision}｜风险等级：${payload.risk_level}｜最终分：${payload.final_score}\n\n${JSON.stringify(payload, null, 2)}`;
  } catch (error) {
    result.textContent = `请求失败：${error.message}`;
    if (requestStatus) {
      requestStatus.textContent = "系统请求失败";
      requestStatus.className = "component-state off";
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  updateClock();
  window.setInterval(updateClock, 1000);
  const form = document.getElementById("risk-check-form");
  if (form) form.addEventListener("submit", submitRiskCheck);
  const picker = document.getElementById("demo-event-picker");
  if (picker && form) {
    const applyDemoEvent = () => {
      const [scenario, sourceId, userId] = picker.value.split("|");
      form.elements.scenario.value = scenario;
      form.elements.source_id.value = sourceId;
      form.elements.user_id.value = userId;
      form.elements.event_data.value = "{}";
    };
    picker.addEventListener("change", applyDemoEvent);
    applyDemoEvent();
  }
  loadRules();
  loadDashboard();
  loadAssessments();
  loadCases();
  wireCaseReview();
  wireAppealPortal();
  wireAgentChat();
  wireGraphQuery();
});

async function loadRules() {
  const body = document.getElementById("rule-table-body");
  if (!body) return;
  const count = document.getElementById("rule-count");
  try {
    const response = await fetch("/api/risk/rules");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const rules = await response.json();
    body.replaceChildren(...rules.map((rule) => {
      const row = document.createElement("tr");
      [rule.rule_id, rule.rule_name, rule.scenarios.join(" / "), rule.risk_score,
        rule.risk_level, rule.decision, rule.description].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.appendChild(cell);
      });
      return row;
    }));
    count.textContent = `${rules.length} 条`;
    count.className = "component-state on";
  } catch (error) {
    body.innerHTML = `<tr><td colspan="7">规则加载失败：${error.message}</td></tr>`;
    count.textContent = "加载失败";
  }
}

async function apiPayload(response) {
  const payload = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item) => item.msg).join("；")
      : (payload.detail || `HTTP ${response.status}`);
    throw new Error(detail);
  }
  return payload;
}

function setAppealFormValue(form, name, value) {
  if (form?.elements[name] && value) form.elements[name].value = value;
}

function wireAppealPortal() {
  const submitForm = document.getElementById("appeal-submit-form");
  const queryForm = document.getElementById("appeal-query-form");
  const evidenceForm = document.getElementById("appeal-evidence-form");
  if (!submitForm && !queryForm && !evidenceForm) return;

  let context = {};
  try { context = JSON.parse(window.sessionStorage.getItem("bankrisk_appeal_context") || "{}"); }
  catch (error) { context = {}; }
  setAppealFormValue(submitForm, "assessment_id", context.assessment_id);
  setAppealFormValue(submitForm, "appeal_token", context.appeal_token);
  setAppealFormValue(queryForm, "appeal_token", context.appeal_token);
  setAppealFormValue(evidenceForm, "appeal_token", context.appeal_token);

  if (submitForm) submitForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(submitForm);
    const target = document.getElementById("appeal-submit-result");
    try {
      const response = await fetch("/api/client/appeals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assessment_id: data.get("assessment_id"),
          appeal_token: data.get("appeal_token"),
          reason: data.get("reason"),
          requested_resolution: data.get("requested_resolution") || null,
        }),
      });
      const payload = await apiPayload(response);
      target.textContent = JSON.stringify(payload, null, 2);
      const updated = {
        assessment_id: payload.assessment_id,
        appeal_id: payload.appeal_id,
        appeal_token: data.get("appeal_token"),
      };
      window.sessionStorage.setItem("bankrisk_appeal_context", JSON.stringify(updated));
      setAppealFormValue(queryForm, "appeal_id", updated.appeal_id);
      setAppealFormValue(queryForm, "appeal_token", updated.appeal_token);
      setAppealFormValue(evidenceForm, "appeal_id", updated.appeal_id);
      setAppealFormValue(evidenceForm, "appeal_token", updated.appeal_token);
    } catch (error) { target.textContent = `申诉提交失败：${error.message}`; }
  });

  if (queryForm) queryForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(queryForm);
    const target = document.getElementById("appeal-query-result");
    try {
      const response = await fetch(`/api/client/appeals/${encodeURIComponent(data.get("appeal_id"))}`, {
        headers: { "X-Appeal-Token": data.get("appeal_token") },
      });
      target.textContent = JSON.stringify(await apiPayload(response), null, 2);
    } catch (error) { target.textContent = `申诉查询失败：${error.message}`; }
  });

  if (evidenceForm) evidenceForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(evidenceForm);
    const target = document.getElementById("appeal-evidence-result");
    try {
      const response = await fetch(`/api/client/appeals/${encodeURIComponent(data.get("appeal_id"))}/evidence`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Appeal-Token": data.get("appeal_token") },
        body: JSON.stringify({
          evidence_type: data.get("evidence_type"),
          statement: data.get("statement") || null,
          file_name: data.get("file_name") || null,
          file_sha256: data.get("file_sha256") || null,
        }),
      });
      target.textContent = JSON.stringify(await apiPayload(response), null, 2);
    } catch (error) { target.textContent = `材料提交失败：${error.message}`; }
  });
}

async function loadDashboard() {
  const target = document.getElementById("metric-assessments");
  if (!target) return;
  try {
    const [overviewResponse, modelResponse] = await Promise.all([
      fetch("/api/dashboard/overview"), fetch("/api/models/status"),
    ]);
    const overview = await overviewResponse.json();
    const models = await modelResponse.json();
    target.textContent = overview.total_assessments;
    document.getElementById("metric-pass-rate").textContent = `${overview.pass_rate}%`;
    document.getElementById("metric-cases").textContent = overview.pending_cases;
    document.getElementById("metric-appeals").textContent = overview.pending_appeals;
    document.getElementById("metric-models").textContent = `${Object.values(models.models).filter((item) => item.ready).length}/5`;
    const note = document.getElementById("dashboard-status-note");
    if (note) note.textContent = `已成功完成 ${overview.total_assessments} 次评估：通过 ${overview.pass_count} 次，触发风控策略 ${overview.risk_action_count} 次。“标记 / 人工审核 / 拒绝”不代表系统失败。`;
  } catch (error) { target.textContent = "--"; }
}

function appendCells(row, values) {
  values.forEach((value) => {
    const cell = document.createElement("td");
    cell.textContent = value ?? "--";
    row.appendChild(cell);
  });
}

async function loadAssessments() {
  const body = document.getElementById("assessment-table-body");
  if (!body) return;
  try {
    const payload = await (await fetch("/api/assessments?page_size=100")).json();
    body.replaceChildren(...payload.items.map((item) => {
      const row = document.createElement("tr");
      appendCells(row, [item.assessment_id, item.scenario, item.user_id, item.rule_score,
        item.model_score, item.graph_score, item.final_score, item.risk_level, item.decision]);
      return row;
    }));
  } catch (error) { body.textContent = `加载失败：${error.message}`; }
}

async function loadCases() {
  const body = document.getElementById("case-table-body");
  if (!body) return;
  try {
    const payload = await (await fetch("/api/cases?page_size=100")).json();
    body.replaceChildren(...payload.items.map((item) => {
      const row = document.createElement("tr");
      appendCells(row, [item.case_id, item.user_id, item.scenario, item.status, item.created_at]);
      row.addEventListener("click", () => { document.querySelector("#case-review-form [name=case_id]").value = item.case_id; });
      return row;
    }));
  } catch (error) { body.textContent = `加载失败：${error.message}`; }
}

function wireCaseReview() {
  const form = document.getElementById("case-review-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const result = document.getElementById("case-review-result");
    const response = await fetch(`/api/cases/${encodeURIComponent(data.get("case_id"))}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: data.get("decision"), reviewer: data.get("reviewer"), comment: data.get("comment") }),
    });
    result.textContent = JSON.stringify(await response.json(), null, 2);
    loadCases();
  });
}

let agentSessionId = null;
function wireAgentChat() {
  const form = document.getElementById("agent-chat-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = form.elements.message;
    const messages = document.getElementById("agent-messages");
    const userNode = document.createElement("div");
    userNode.className = "chat-message user";
    userNode.textContent = input.value;
    messages.appendChild(userNode);
    const response = await fetch("/api/agent/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: input.value, session_id: agentSessionId }) });
    const payload = await response.json();
    agentSessionId = payload.session_id;
    const replyNode = document.createElement("div");
    replyNode.className = "chat-message assistant";
    replyNode.textContent = payload.reply || payload.detail;
    messages.appendChild(replyNode);
    messages.scrollTop = messages.scrollHeight;
    input.value = "";
  });
}

function wireGraphQuery() {
  const form = document.getElementById("graph-query-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const payload = await (await fetch(`/api/graph/users/${encodeURIComponent(data.get("user_id"))}?depth=${data.get("depth")}`)).json();
    document.getElementById("graph-summary").textContent = JSON.stringify({ community_size: payload.community_size, nodes: payload.nodes.length, edges: payload.edges.length, backend: payload.backend }, null, 2);
    renderGraph(payload);
  });
  form.requestSubmit();
}

function renderGraph(payload) {
  const svg = document.getElementById("graph-canvas");
  svg.replaceChildren();
  const namespace = "http://www.w3.org/2000/svg";
  const positions = new Map();
  payload.nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, payload.nodes.length);
    positions.set(node.id, { x: 400 + Math.cos(angle) * 190, y: 240 + Math.sin(angle) * 170 });
  });
  payload.edges.forEach((edge) => {
    const from = positions.get(edge.source); const to = positions.get(edge.target);
    if (!from || !to) return;
    const line = document.createElementNS(namespace, "line");
    line.setAttribute("x1", from.x); line.setAttribute("y1", from.y); line.setAttribute("x2", to.x); line.setAttribute("y2", to.y); line.setAttribute("class", "graph-edge"); svg.appendChild(line);
  });
  payload.nodes.forEach((node) => {
    const position = positions.get(node.id);
    const circle = document.createElementNS(namespace, "circle");
    circle.setAttribute("cx", position.x); circle.setAttribute("cy", position.y); circle.setAttribute("r", node.entity_type === "USER" ? 14 : 9); circle.setAttribute("class", `graph-node ${node.entity_type.toLowerCase()}`); svg.appendChild(circle);
    const text = document.createElementNS(namespace, "text");
    text.setAttribute("x", position.x + 12); text.setAttribute("y", position.y - 10); text.textContent = node.entity_id; svg.appendChild(text);
  });
}
