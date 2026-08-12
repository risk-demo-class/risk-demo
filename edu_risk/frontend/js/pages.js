/* ============================================================
   pages.js — 10 个页面逻辑 + 路由 + 初始化
   对接 EduRisk FastAPI 后端（api.js 封装见 core.js）
   ============================================================ */
'use strict';

const DEC_COLOR = { '通过': '#16a34a', '标记': '#2563eb', '人工审核': '#f59e0b', '拒绝': '#dc2626' };
const PAGE_TITLES = {
  dashboard: '运营仪表盘', check: '风控检查', cases: '案件工作台', rules: '规则管理',
  users: '学员画像', blacklist: '黑名单管理', events: '风控事件',
  business: '业务数据', settings: '系统设置', agent: 'AI 助手',
};
let currentPage = 'dashboard';

/* ================= 路由 & 健康检查 ================= */
function switchPage(name) {
  currentPage = name;
  document.querySelectorAll('.page').forEach((p) => p.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.querySelectorAll('.menu-item').forEach((m) => m.classList.toggle('active', m.dataset.page === name));
  document.getElementById('page-title').textContent = PAGE_TITLES[name];
  refreshPage();
}

function refreshPage() {
  const loaders = {
    dashboard: loadDashboard, check: () => {}, cases: loadCases,
    rules: loadRules, users: () => {}, blacklist: loadBlacklist,
    events: loadEvents, business: loadBusiness, settings: loadSettings, agent: () => {},
  };
  try { (loaders[currentPage] || (() => {}))(); } catch (e) { /* ignore */ }
}

async function healthCheck() {
  const dot = document.getElementById('health-dot');
  const txt = document.getElementById('health-text');
  try {
    const h = await apiGet('/api/health');
    dot.className = 'health-dot ok';
    txt.textContent = '后端已连接 · ML ' + (h.ml_model_loaded ? '已加载' : '未加载');
  } catch (e) {
    dot.className = 'health-dot bad';
    txt.textContent = '后端未连接（' + API_BASE + '）';
  }
}

/* ================= 1. 运营仪表盘 ================= */
async function loadDashboard() {
  const days = document.getElementById('dash-days').value;
  const tip = `近 ${days} 天`;
  document.getElementById('stat-checks-sub').textContent = tip;
  document.getElementById('stat-enroll-sub').textContent = tip;
  document.getElementById('stat-pay-sub').textContent = tip;
  document.getElementById('stat-refund-sub').textContent = tip;
  document.getElementById('trend-tip').textContent = tip;

  try {
    const s = await apiGet(`/api/dashboard/stats?days=${days}`);
    document.getElementById('stat-checks').textContent = fmtNum(s.total_checks);
    document.getElementById('stat-pending').textContent = fmtNum(s.pending_cases);
    const bv = s.business_volume || {};
    document.getElementById('stat-enroll').textContent = fmtNum(bv.enrollments);
    document.getElementById('stat-pay').textContent = fmtNum(bv.payments);
    document.getElementById('stat-refund').textContent = fmtNum(bv.refunds);
    const dist = s.decision_distribution || {};
    svgDonut(document.getElementById('chart-decision'),
      ['通过', '标记', '人工审核', '拒绝'].map((k) => ({
        label: k, value: dist[k] || 0, color: DEC_COLOR[k],
      })), { center: '决策' });
  } catch (e) {
    toast('仪表盘统计加载失败：' + e.message, 'error');
  }

  try {
    const t = await apiGet(`/api/dashboard/trend?days=${days}`);
    svgLineChart(document.getElementById('chart-trend'),
      (t.trend || []).map((x) => ({ label: String(x.date).slice(5), value: x.count })),
      { color: '#2563eb' });
  } catch (e) { /* 静默 */ }

  try {
    const r = await apiGet('/api/dashboard/rule-effectiveness');
    document.getElementById('rule-eff-tip').textContent = `最近 ${fmtNum(r.total_assessments)} 次评估 · TOP 10`;
    svgBars(document.getElementById('chart-rules'),
      (r.rule_hits || []).slice(0, 10).map((x) => ({ label: x.rule_id, value: x.count, sub: x.rate })),
      { color: '#0ea5e9' });
  } catch (e) { /* 静默 */ }
}

/* ================= 2. 风控检查 ================= */
function gaugeSVG(score, color) {
  const size = 120, thick = 11, R = (size - thick) / 2, C = size / 2;
  const circ = 2 * Math.PI * R;
  const frac = Math.min(100, Math.max(0, Number(score) || 0)) / 100;
  const len = frac * circ;
  return `<svg viewBox="0 0 ${size} ${size}" style="width:120px;height:120px">
    <circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="#eef1f5" stroke-width="${thick}"/>
    <circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="${color}" stroke-width="${thick}"
      stroke-linecap="round" stroke-dasharray="${len.toFixed(1)} ${circ.toFixed(1)}"
      transform="rotate(-90 ${C} ${C})"/>
  </svg>`;
}

async function submitCheck() {
  const form = document.getElementById('check-form');
  const fd = new FormData(form);
  let extra = {};
  try { extra = parseExtra(fd.get('extra')); }
  catch (e) { toast('extra 不是合法 JSON：' + e.message, 'error'); return; }

  const btn = document.getElementById('btn-check');
  btn.disabled = true; btn.textContent = '⏳ 检查中…';
  const box = document.getElementById('check-result');
  box.classList.remove('hidden');
  box.innerHTML = '<div class="empty">正在执行 7 步风控流水线…</div>';
  try {
    const r = await apiPost('/api/risk/check', {
      event_type: fd.get('event_type'), source_id: fd.get('source_id'),
      user_id: fd.get('user_id'), extra,
    });
    box.innerHTML = renderCheckResult(r);
  } catch (e) {
    box.innerHTML = `<div class="card"><div class="empty" style="color:#dc2626">检查失败：${esc(e.message)}</div></div>`;
  } finally {
    btn.disabled = false; btn.textContent = '🚀 开始风控检查';
  }
}

function renderCheckResult(r) {
  const lvColor = LEVEL_COLOR[r.risk_level] || '#64748b';
  const hitRows = (r.hit_rules || []).map((h) => `
    <tr>
      <td class="mono">${esc(h.rule_id)}</td>
      <td>${esc(h.rule_name)}</td>
      <td><span class="badge ${LEVEL_CLASS[h.risk_level] || 'badge-gray'}">${esc(h.risk_level)}</span></td>
      <td class="td-num">${fmtNum(h.risk_score)}</td>
      <td><span class="badge ${DECISION_CLASS[h.action] || 'badge-gray'}">${esc(h.action)}</span></td>
      <td class="muted">${esc(h.description || h.rule_category || '—')}</td>
    </tr>`).join('') || emptyRow(6, '未命中任何规则');

  const feats = Object.entries(r.features || {}).map(([k, v]) => `
    <div class="feat-item"><div class="fv-name">${esc(k)}</div>
      <div class="fv-val">${fmtNum(v)}</div></div>`).join('');

  return `
  <div class="result-banner">
    <div class="gauge-wrap">
      ${gaugeSVG(r.final_score, lvColor)}
      <div class="gauge-num"><b style="color:${lvColor}">${fmtNum(r.final_score)}</b><span>综合风险分</span></div>
    </div>
    <div style="flex:1;min-width:260px">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
        <span class="badge ${DECISION_CLASS[r.decision] || 'badge-gray'}" style="font-size:14px;padding:4px 14px">决策：${esc(r.decision)}</span>
        <span class="badge ${LEVEL_CLASS[r.risk_level] || 'badge-gray'}" style="font-size:14px;padding:4px 14px">风险等级：${esc(r.risk_level)}</span>
      </div>
      <div class="result-meta">
        <div class="meta-chip"><div class="mc-label">规则分</div><div class="mc-value">${fmtNum(r.rule_score)}</div></div>
        <div class="meta-chip"><div class="mc-label">ML 分</div><div class="mc-value">${fmtNum(r.ml_score)}<span style="font-size:11px;color:#94a3b8">${r.ml_loaded ? '' : '(未加载)'}</span></div></div>
        <div class="meta-chip"><div class="mc-label">事件 ID</div><div class="mc-value mono" style="font-size:13px">${esc(r.event_id)}</div></div>
        <div class="meta-chip"><div class="mc-label">案件 ID</div><div class="mc-value mono" style="font-size:13px">${esc(r.case_id || '—')}</div></div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-head"><h3>命中规则（${(r.hit_rules || []).length}）</h3></div>
    <table class="table"><thead><tr><th>规则 ID</th><th>规则名称</th><th>等级</th><th>分值</th><th>动作</th><th>说明</th></tr></thead>
    <tbody>${hitRows}</tbody></table>
  </div>

  <div class="card">
    <div class="card-head"><h3>特征快照（${Object.keys(r.features || {}).length} 维）</h3>
      <button class="btn btn-sm btn-light" onclick="document.getElementById('feat-grid').classList.toggle('hidden')">折叠/展开</button></div>
    <div id="feat-grid" class="feat-grid">${feats}</div>
  </div>`;
}

/* ================= 3. 案件工作台 ================= */
let casePage = 1;
async function loadCases() {
  const statusSel = document.getElementById('case-status').value;
  const user = document.getElementById('case-user').value.trim();
  let qs = `page=${casePage}&page_size=15`;
  if (statusSel === 'active') qs += '&active_only=true';
  else if (statusSel) qs += '&status=' + encodeURIComponent(statusSel);
  if (user) qs += '&user_id=' + encodeURIComponent(user);
  const tbody = document.getElementById('case-tbody');
  tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#94a3b8;padding:36px 0">加载中…</td></tr>';
  try {
    const d = await apiGet('/api/cases?' + qs);
    const items = d.items || [];
    tbody.innerHTML = items.length ? items.map((c) => {
      const canClaim = c.case_status === '待审核';
      const canReview = c.case_status === '审核中';
      const canClose = ['待审核', '审核中'].includes(c.case_status);
      return `<tr>
        <td class="mono">${esc(c.case_id)}</td>
        <td class="mono">${esc(c.user_id)}</td>
        <td class="mono">${esc(c.source_id)}</td>
        <td>${esc(c.event_type)}</td>
        <td><span class="badge ${CASE_STATUS_CLASS[c.case_status] || 'badge-gray'}">${esc(c.case_status)}</span></td>
        <td class="muted">${esc(c.assignee || c.reviewer || '—')}</td>
        <td class="muted">${fmtTime(c.create_time)}</td>
        <td class="td-actions">
          ${canClaim ? `<button class="btn btn-sm btn-light" onclick="openClaim('${c.case_id}')">领取</button>` : ''}
          ${canReview ? `<button class="btn btn-sm btn-primary" onclick="openReview('${c.case_id}','approve')">通过</button>
            <button class="btn btn-sm btn-danger" onclick="openReview('${c.case_id}','reject')">拒绝</button>` : ''}
          ${canClose ? `<button class="btn btn-sm btn-ghost" onclick="openClose('${c.case_id}')">关闭</button>` : ''}
        </td>
      </tr>`;
    }).join('') : emptyRow(8, '暂无案件');
    renderPagination(document.getElementById('case-pagination'),
      { page: casePage, pageSize: 15, total: d.total || items.length,
        onChange: (p) => { casePage = p; loadCases(); } });
  } catch (e) {
    tbody.innerHTML = emptyRow(8, '加载失败：' + esc(e.message));
  }
}

function promptOperator(placeholder = '操作人（如 ops_admin）') {
  return `<div class="form-item"><label class="lbl">操作人</label>
    <input id="dlg-operator" class="input" placeholder="${placeholder}" value="ops_admin"></div>`;
}

function openClaim(caseId) {
  openModal({
    title: '领取案件 ' + caseId, wide: false,
    body: promptOperator() + '<div class="mt-8 muted" style="font-size:12px">领取后案件状态：待审核 → 审核中</div>',
    footer: `<button class="btn btn-light" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" id="dlg-ok">确认领取</button>`,
  });
  document.getElementById('dlg-ok').onclick = async () => {
    const operator = document.getElementById('dlg-operator').value.trim() || 'ops_admin';
    try {
      await apiPost(`/api/cases/${caseId}/claim`, { operator });
      toast('领取成功', 'success'); closeModal(); loadCases();
    } catch (e) { toast(e.message, 'error'); }
  };
}

function openReview(caseId, action) {
  const title = action === 'approve' ? '通过案件' : '拒绝案件';
  openModal({
    title: `${title} ${caseId}`, wide: false,
    body: promptOperator() + `
      <div class="form-item mt-8"><label class="lbl">审核意见</label>
        <textarea id="dlg-comment" class="input area" rows="3" placeholder="填写审核意见（可选）"></textarea></div>`,
    footer: `<button class="btn btn-light" onclick="closeModal()">取消</button>
      <button class="btn ${action === 'approve' ? 'btn-primary' : 'btn-danger'}" id="dlg-ok">确认${action === 'approve' ? '通过' : '拒绝'}</button>`,
  });
  document.getElementById('dlg-ok').onclick = async () => {
    const operator = document.getElementById('dlg-operator').value.trim() || 'ops_admin';
    const comment = document.getElementById('dlg-comment').value.trim();
    try {
      await apiPost(`/api/cases/${caseId}/review`, { action, operator, comment });
      toast(action === 'approve' ? '已通过' : '已拒绝', 'success'); closeModal(); loadCases();
    } catch (e) { toast(e.message, 'error'); }
  };
}

function openClose(caseId) {
  openModal({
    title: '关闭案件 ' + caseId, wide: false,
    body: promptOperator() + `
      <div class="form-item mt-8"><label class="lbl">关闭原因</label>
        <input id="dlg-comment" class="input" placeholder="默认：手动关闭"></div>`,
    footer: `<button class="btn btn-light" onclick="closeModal()">取消</button>
      <button class="btn btn-warn" id="dlg-ok">确认关闭</button>`,
  });
  document.getElementById('dlg-ok').onclick = async () => {
    const operator = document.getElementById('dlg-operator').value.trim() || 'ops_admin';
    const comment = document.getElementById('dlg-comment').value.trim();
    try {
      await apiPost(`/api/cases/${caseId}/close`, { operator, comment });
      toast('案件已关闭', 'success'); closeModal(); loadCases();
    } catch (e) { toast(e.message, 'error'); }
  };
}

/* ================= 4. 规则管理 ================= */
async function loadRules() {
  const ft = document.getElementById('rule-filter').value;
  const qs = ft ? '?event_type=' + encodeURIComponent(ft) : '';
  const tbody = document.getElementById('rule-tbody');
  tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:#94a3b8;padding:36px 0">加载中…</td></tr>';
  try {
    const rules = await apiGet('/api/rules' + qs);
    tbody.innerHTML = rules.length ? rules.map((r) => `
      <tr>
        <td class="mono">${esc(r.rule_id)}</td>
        <td>${esc(r.rule_name)}</td>
        <td><span class="badge badge-gray">${esc(r.rule_category)}</span></td>
        <td>${esc(r.event_type)}</td>
        <td><span class="badge ${LEVEL_CLASS[r.risk_level] || 'badge-gray'}">${esc(r.risk_level)}</span></td>
        <td class="td-num">${fmtNum(r.risk_score)}</td>
        <td><span class="badge ${DECISION_CLASS[r.action] || 'badge-gray'}">${esc(r.action)}</span></td>
        <td class="td-num">${fmtNum(r.priority)}</td>
        <td><label class="switch"><input type="checkbox" ${r.is_enabled ? 'checked' : ''} onchange="toggleRule('${r.rule_id}', this.checked)"><span class="slider"></span></label></td>
        <td class="muted" style="max-width:200px">${esc(r.description || '')}</td>
      </tr>`).join('') : emptyRow(10, '暂无规则');
  } catch (e) {
    tbody.innerHTML = emptyRow(10, '加载失败：' + esc(e.message));
  }
}

async function toggleRule(ruleId, enabled) {
  try {
    await api(`/api/rules/${ruleId}/toggle?is_enabled=${enabled}`, { method: 'PATCH' });
    toast(`规则 ${ruleId} 已${enabled ? '启用' : '停用'}`, 'success');
  } catch (e) { toast(e.message, 'error'); loadRules(); }
}

function openNewRule() {
  openModal({
    title: '新建风控规则', wide: true,
    body: `
    <div class="form-grid" style="grid-template-columns:1fr 1fr">
      <div class="form-item"><label class="lbl">规则 ID</label><input id="r-rule_id" class="input mono" placeholder="如 R031"></div>
      <div class="form-item"><label class="lbl">规则名称</label><input id="r-rule_name" class="input" placeholder="如 新账号大额缴费"></div>
      <div class="form-item"><label class="lbl">类别</label><input id="r-rule_category" class="input" placeholder="报名/缴费/退费/考试/账号/内容" value="通用"></div>
      <div class="form-item"><label class="lbl">事件类型</label><select id="r-event_type" class="input sel">
        <option value="通用">通用</option><option value="报名">报名</option><option value="缴费">缴费</option>
        <option value="退费">退费</option><option value="考试">考试</option><option value="作业">作业</option></select></div>
      <div class="form-item"><label class="lbl">风险等级</label><select id="r-risk_level" class="input sel">
        <option value="低">低</option><option value="中" selected>中</option><option value="高">高</option><option value="极高">极高</option></select></div>
      <div class="form-item"><label class="lbl">风险分值</label><input id="r-risk_score" class="input" type="number" value="40"></div>
      <div class="form-item"><label class="lbl">动作</label><select id="r-action" class="input sel">
        <option value="标记" selected>标记</option><option value="人工审核">人工审核</option><option value="拒绝">拒绝</option><option value="通过">通过</option></select></div>
      <div class="form-item"><label class="lbl">优先级（越大越先匹配）</label><input id="r-priority" class="input" type="number" value="50"></div>
      <div class="form-item form-item-wide"><label class="lbl">说明</label><input id="r-description" class="input" placeholder="可选"></div>
      <div class="form-item form-item-wide"><label class="lbl">条件表达式 rule_condition（JSON）</label>
        <textarea id="r-condition" class="input area mono" rows="4" placeholder='{"and":[{"field":"acct_is_new","op":"==","value":1},{"field":"enroll_total_amount","op":">=","value":30000}]}'></textarea>
        <div class="muted" style="font-size:11px;margin-top:4px">支持的 op：&gt; &gt;= &lt; &lt;= == != in not_in between；可组合 and / or</div></div>
    </div>`,
    footer: `<button class="btn btn-light" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" id="dlg-ok">创建规则</button>`,
  });
  document.getElementById('dlg-ok').onclick = async () => {
    try {
      let cond; try { cond = JSON.parse(document.getElementById('r-condition').value); }
      catch (e) { throw new Error('条件表达式不是合法 JSON'); }
      const payload = {
        rule_id: document.getElementById('r-rule_id').value.trim(),
        rule_name: document.getElementById('r-rule_name').value.trim(),
        rule_category: document.getElementById('r-rule_category').value.trim(),
        event_type: document.getElementById('r-event_type').value,
        rule_condition: cond,
        risk_level: document.getElementById('r-risk_level').value,
        risk_score: Number(document.getElementById('r-risk_score').value) || 40,
        action: document.getElementById('r-action').value,
        priority: Number(document.getElementById('r-priority').value) || 50,
        description: document.getElementById('r-description').value.trim(),
        is_enabled: true,
      };
      if (!payload.rule_id) throw new Error('规则 ID 必填');
      if (!payload.rule_name) throw new Error('规则名称必填');
      await apiPost('/api/rules', payload);
      toast('规则创建成功', 'success'); closeModal(); loadRules();
    } catch (e) { toast(e.message, 'error'); }
  };
}

function openTestRule() {
  openModal({
    title: '规则测试 · POST /api/rules/test', wide: true,
    body: `
    <div class="form-item"><label class="lbl">条件表达式 rule_condition（JSON）</label>
      <textarea id="t-condition" class="input area mono" rows="4" placeholder='{"and":[{"field":"acct_is_new","op":"==","value":1},{"field":"enroll_total_amount","op":">=","value":30000}]}'></textarea></div>
    <div class="form-item mt-8"><label class="lbl">特征 features（JSON）</label>
      <textarea id="t-features" class="input area mono" rows="4" placeholder='{"acct_is_new":1,"enroll_total_amount":50000}'></textarea></div>
    <div class="mt-14" id="t-result"></div>`,
    footer: `<button class="btn btn-light" onclick="closeModal()">关闭</button>
      <button class="btn btn-primary" id="dlg-ok">执行测试</button>`,
  });
  document.getElementById('dlg-ok').onclick = async () => {
    const box = document.getElementById('t-result');
    try {
      const cond = JSON.parse(document.getElementById('t-condition').value);
      const feats = JSON.parse(document.getElementById('t-features').value);
      if (typeof feats !== 'object' || Array.isArray(feats)) throw new Error('features 必须是 JSON 对象');
      box.innerHTML = '<div class="empty">测试中…</div>';
      const r = await apiPost('/api/rules/test', { rule_condition: cond, features: feats });
      box.innerHTML = r.hit
        ? `<div class="badge badge-red" style="font-size:14px;padding:6px 16px">✔ 命中（condition 为 true）</div>`
        : `<div class="badge badge-green" style="font-size:14px;padding:6px 16px">✘ 未命中（condition 为 false）</div>`;
    } catch (e) { box.innerHTML = `<div style="color:#dc2626;font-size:13px">错误：${esc(e.message)}</div>`; }
  };
}

/* ================= 5. 学员画像 ================= */
async function queryUserProfile() {
  const uid = document.getElementById('user-id-input').value.trim();
  const box = document.getElementById('user-profile');
  if (!uid) { toast('请输入学员 ID', 'error'); return; }
  box.classList.remove('hidden');
  box.innerHTML = '<div class="card"><div class="empty">查询中…</div></div>';
  try {
    const u = await apiGet(`/api/users/${encodeURIComponent(uid)}/profile`);
    const p = u.profile || {};
    const tagColor = p.risk_tag === '高危' ? 'badge-red' : (p.risk_tag === '关注' ? 'badge-orange' : 'badge-green');
    box.innerHTML = `
    <div class="result-banner" style="flex-direction:column;align-items:flex-start;gap:14px">
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <div style="font-size:18px;font-weight:800">${esc(u.user_name || uid)}</div>
        <span class="badge badge-blue">${esc(u.user_level || '普通')}学员</span>
        <span class="badge ${tagColor}">风险标签：${esc(p.risk_tag || '正常')}</span>
        ${u.in_blacklist
          ? `<span class="badge badge-red">🚫 已拉黑：${esc(u.blacklist_reason || '')}</span>`
          : '<span class="badge badge-green">不在黑名单</span>'}
      </div>
      <div class="muted mono" style="font-size:12px">学员 ID：${esc(u.user_id)} · 注册时间：${fmtTime(u.register_time)}</div>
    </div>
    <div class="profile-grid">
      <div class="profile-card"><div class="pc-label">累计检查次数</div><div class="pc-value">${fmtNum(p.total_checks)}</div></div>
      <div class="profile-card"><div class="pc-label">累计案件数</div><div class="pc-value">${fmtNum(p.total_cases)}</div></div>
      <div class="profile-card"><div class="pc-label">历史最高分</div><div class="pc-value" style="color:${LEVEL_COLOR[p.risk_tag === '高危' ? '极高' : (p.risk_tag === '关注' ? '高' : '低')]}">${fmtNum(p.max_score)}</div></div>
      <div class="profile-card"><div class="pc-label">平均分</div><div class="pc-value">${fmtNum(p.avg_score)}</div></div>
    </div>`;
  } catch (e) {
    box.innerHTML = `<div class="card"><div class="empty" style="color:#dc2626">查询失败：${esc(e.message)}</div></div>`;
  }
}

/* ================= 6. 黑名单管理 ================= */
async function loadBlacklist() {
  const tbody = document.getElementById('bl-tbody');
  try {
    const rows = await apiGet('/api/blacklist?status=生效');
    document.getElementById('bl-count').textContent = `共 ${rows.length} 条生效`;
    tbody.innerHTML = rows.length ? rows.map((b) => `
      <tr>
        <td class="mono">${esc(b.blacklist_id)}</td>
        <td class="mono">${esc(b.user_id)}</td>
        <td>${esc(b.reason || '—')}</td>
        <td><span class="badge ${b.source === 'AI' ? 'badge-blue' : (b.source === '规则' ? 'badge-orange' : 'badge-gray')}">${esc(b.source)}</span></td>
        <td><span class="badge badge-red">${esc(b.status)}</span></td>
        <td class="muted">${fmtTime(b.create_time)}</td>
        <td class="td-actions"><button class="btn btn-sm btn-light" onclick="releaseBlacklist('${b.blacklist_id}')">解除</button></td>
      </tr>`).join('') : emptyRow(7, '暂无生效黑名单');
  } catch (e) {
    tbody.innerHTML = emptyRow(7, '加载失败：' + esc(e.message));
  }
}

async function addBlacklist() {
  const user_id = document.getElementById('bl-user').value.trim();
  if (!user_id) { toast('请输入学员 ID', 'error'); return; }
  const reason = document.getElementById('bl-reason').value.trim() || '人工拉黑';
  const source = document.getElementById('bl-source').value;
  try {
    await apiPost('/api/blacklist', { user_id, reason, source });
    toast(`已拉黑 ${user_id}`, 'success');
    document.getElementById('bl-form').reset();
    loadBlacklist();
  } catch (e) { toast(e.message, 'error'); }
}

async function releaseBlacklist(blacklistId) {
  if (!confirm('确认解除该黑名单记录？')) return;
  try {
    await apiPost(`/api/blacklist/${blacklistId}/release`);
    toast('已解除', 'success'); loadBlacklist();
  } catch (e) { toast(e.message, 'error'); }
}

/* ================= 7. 风控事件 ================= */
let eventPage = 1;
async function loadEvents() {
  const et = document.getElementById('event-filter').value;
  const user = document.getElementById('event-user').value.trim();
  let qs = `page=${eventPage}&page_size=15`;
  if (et) qs += '&event_type=' + encodeURIComponent(et);
  if (user) qs += '&user_id=' + encodeURIComponent(user);
  const tbody = document.getElementById('event-tbody');
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:36px 0">加载中…</td></tr>';
  try {
    const d = await apiGet('/api/events?' + qs);
    const items = d.items || [];
    tbody.innerHTML = items.length ? items.map((e) => `
      <tr>
        <td class="mono">${esc(e.event_id)}</td>
        <td><span class="badge badge-blue">${esc(e.event_type)}</span></td>
        <td class="mono">${esc(e.user_id)}</td>
        <td class="mono">${esc(e.source_id)}</td>
        <td class="muted">${fmtTime(e.create_time)}</td>
        <td class="td-actions"><button class="btn btn-sm btn-light" onclick="openEventDetail('${e.event_id}')">详情</button></td>
      </tr>`).join('') : emptyRow(6, '暂无事件');
    renderPagination(document.getElementById('event-pagination'),
      { page: eventPage, pageSize: 15, total: d.total || items.length,
        onChange: (p) => { eventPage = p; loadEvents(); } });
  } catch (e) {
    tbody.innerHTML = emptyRow(6, '加载失败：' + esc(e.message));
  }
}

async function openEventDetail(eventId) {
  openModal({ title: '事件详情 ' + eventId, wide: true, body: '<div class="empty">加载中…</div>', footer: '<button class="btn btn-light" onclick="closeModal()">关闭</button>' });
  try {
    const r = await apiGet(`/api/risk/check/${eventId}`);
    const a = r.assessment || {};
    const feats = Object.entries(r.features || {});
    document.getElementById('modal-body').innerHTML = `
      ${detailTable([
        ['事件 ID', r.event_id], ['事件类型', r.event_type], ['学员 ID', r.user_id],
        ['业务单据号', r.source_id], ['时间', fmtTime(r.create_time)],
        ['最终评分', `${fmtNum(a.final_score)}（规则 ${fmtNum(a.rule_score)} / ML ${fmtNum(a.ml_score)}）`],
        ['风险等级', r.risk_level || a.risk_level], ['决策', a.decision],
      ])}
      <h3 class="mt-14" style="font-size:14px">特征快照（${feats.length} 维）</h3>
      <div class="feat-grid mt-8">${feats.map(([k, v]) => `<div class="feat-item"><div class="fv-name">${esc(k)}</div><div class="fv-val">${fmtNum(v)}</div></div>`).join('')}</div>`;
  } catch (e) {
    document.getElementById('modal-body').innerHTML = `<div class="empty" style="color:#dc2626">加载失败：${esc(e.message)}</div>`;
  }
}

/* ================= 8. 业务数据 ================= */
const BIZ_COLS = {
  courses: [
    ['course_id', '课程 ID'], ['course_name', '课程名称'], ['price', '价格', 'money'],
    ['category_id', '分类'], ['school_id', '校区'],
  ],
  enrollments: [
    ['enrollment_id', '报名单 ID'], ['user_id', '学员'], ['status', '状态'],
    ['total_amount', '总金额', 'money'], ['create_time', '报名时间', 'time'],
  ],
  payments: [
    ['payment_id', '缴费单 ID'], ['enrollment_id', '报名单'], ['user_id', '学员'],
    ['amount', '金额', 'money'], ['pay_method', '支付方式'], ['status', '状态'], ['pay_time', '缴费时间', 'time'],
  ],
  refunds: [
    ['refund_id', '退费单 ID'], ['enrollment_id', '报名单'], ['user_id', '学员'],
    ['amount', '金额', 'money'], ['reason', '原因'], ['status', '状态'], ['apply_time', '申请时间', 'time'],
  ],
  exams: [
    ['exam_id', '考试 ID'], ['user_id', '学员'], ['course_id', '课程'],
    ['duration_seconds', '时长(秒)', 'num'], ['score', '成绩', 'num'],
    ['cheat_flag', '作弊标记', 'flag'], ['exam_time', '考试时间', 'time'],
  ],
};
let bizType = 'courses';

function renderBizHead(cols) {
  document.getElementById('biz-thead').innerHTML = `<tr>${cols.map((c) => `<th>${c[1]}</th>`).join('')}</tr>`;
}
function renderBizRows(cols, rows) {
  const fmt = {
    money: (v) => fmtMoney(v), time: (v) => fmtTime(v), num: (v) => fmtNum(v),
    flag: (v) => (v ? '<span class="badge badge-red">是</span>' : '<span class="badge badge-green">否</span>'),
    plain: (v) => esc(v ?? '—'),
  };
  return rows.map((r) => `<tr>${cols.map((c) => `<td class="td-num">${fmt[c[2] || 'plain'](r[c[0]])}</td>`).join('')}</tr>`).join('');
}

async function loadBusiness() {
  const cols = BIZ_COLS[bizType];
  renderBizHead(cols);
  const user = document.getElementById('biz-user').value.trim();
  const qs = (user && bizType !== 'courses') ? `?user_id=${encodeURIComponent(user)}` : '';
  const tbody = document.getElementById('biz-tbody');
  tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:#94a3b8;padding:36px 0">加载中…</td></tr>';
  try {
    const rows = await apiGet(`/api/business/${bizType}${qs}`);
    tbody.innerHTML = rows.length ? renderBizRows(cols, rows) : emptyRow(cols.length, '暂无数据');
  } catch (e) {
    tbody.innerHTML = emptyRow(cols.length, '加载失败：' + esc(e.message));
  }
}

/* ================= 9. 系统设置 ================= */
async function loadSettings() {
  const box = document.getElementById('settings-body');
  box.innerHTML = '<div class="empty">加载中…</div>';
  try {
    const s = await apiGet('/api/settings');
    const t = s.decision_thresholds || {};
    const f = s.fusion || {};
    const al = s.alerts || {};
    box.innerHTML = `
    <div class="stat-cards" style="grid-template-columns:repeat(4,1fr)">
      <div class="stat-card"><div class="sc-label">通过阈值（&lt;）</div><div class="sc-value">${t.pass ?? '—'}</div><div class="sc-sub">0 分 起判通过</div></div>
      <div class="stat-card"><div class="sc-label">标记阈值（&lt;）</div><div class="sc-value">${t.mark ?? '—'}</div><div class="sc-sub">≥通过即标记</div></div>
      <div class="stat-card warn"><div class="sc-label">人工审核阈值（&lt;）</div><div class="sc-value">${t.review ?? '—'}</div><div class="sc-sub">≥标记即人工审核</div></div>
      <div class="stat-card danger"><div class="sc-label">一票否决分</div><div class="sc-value">${t.veto_min ?? '—'}</div><div class="sc-sub">极高规则强制 ≥ 90</div></div>
    </div>
    <div class="chart-row" style="margin-top:18px">
      <div class="card">
        <div class="card-head"><h3>双轨融合权重</h3></div>
        ${detailTable([
          ['规则权重 α', fmtNum(f.alpha_rule)], ['ML 权重 β', fmtNum(f.beta_ml)],
          ['融合公式', 'final = α×rule_score + β×ml_score'],
        ])}
      </div>
      <div class="card">
        <div class="card-head"><h3>告警配置</h3></div>
        ${detailTable([
          ['待审核案件堆积阈值', fmtNum(al.pending_case_threshold)],
          ['规则命中率下限 %', fmtNum(al.rule_hit_rate_min)],
          ['黑名单命中率上限 %', fmtNum(al.blacklist_hit_rate_max)],
          ['检查窗口（小时）', fmtNum(al.check_window_hours)],
        ])}
      </div>
    </div>
    <div class="card">
      <div class="card-head"><h3>案件与模型</h3></div>
      ${detailTable([
        ['案件超时自动关闭（小时）', fmtNum(s.case_timeout_hours)],
        ['XGBoost 启用', s.xgb && s.xgb.enabled ? '是' : '否'],
        ['模型路径', s.xgb ? s.xgb.model_path : '—'],
      ])}
    </div>`;
  } catch (e) {
    box.innerHTML = `<div class="empty" style="color:#dc2626">加载失败：${esc(e.message)}</div>`;
  }
}

/* ================= 10. AI 助手（SSE 流式） ================= */
function appendMsg(role, text) {
  const box = document.getElementById('agent-messages');
  const div = document.createElement('div');
  div.className = 'msg ' + (role === 'user' ? 'msg-user' : 'msg-ai');
  div.innerHTML = `<div class="msg-bubble">${esc(text)}</div>`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function handleSseEvent(raw, aiBubble) {
  let event = 'text', data = '';
  raw.split('\n').forEach((line) => {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data = line.slice(5).trim();
  });
  if (event === 'tool') {
    const box = document.getElementById('agent-messages');
    const div = document.createElement('div');
    div.className = 'msg msg-ai msg-tool';
    div.innerHTML = `<div class="msg-bubble">🔧 ${esc(data)}</div>`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  } else if (event === 'text') {
    if (aiBubble) aiBubble.textContent += (aiBubble.textContent ? '\n' : '') + data;
  } else if (event === 'error') {
    if (aiBubble) {
      aiBubble.parentElement.classList.add('msg-err');
      aiBubble.textContent = '出错了：' + data;
    }
  } else if (event === 'done') {
    if (aiBubble && aiBubble.dataset.cursor) aiBubble.querySelector('.cursor-blink').remove();
  }
}

async function sendAgent() {
  const input = document.getElementById('agent-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  appendMsg('user', msg);

  const box = document.getElementById('agent-messages');
  const aiWrap = document.createElement('div');
  aiWrap.className = 'msg msg-ai';
  aiWrap.innerHTML = `<div class="msg-bubble"><span class="cursor-blink"></span></div>`;
  box.appendChild(aiWrap);
  const aiBubble = aiWrap.querySelector('.msg-bubble');
  aiBubble.dataset.cursor = '1';
  box.scrollTop = box.scrollHeight;

  try {
    const res = await fetch(API_BASE + '/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, session_id: 'default', user_id: 'ops_admin' }),
    });
    if (!res.ok) {
      let detail = 'HTTP ' + res.status;
      try { detail = (await res.json()).detail || detail; } catch (e) { /* */ }
      throw new Error(detail);
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split('\n\n');
      buf = parts.pop();
      parts.forEach((p) => { if (p.trim()) handleSseEvent(p, aiBubble); });
      box.scrollTop = box.scrollHeight;
    }
    if (buf.trim()) handleSseEvent(buf, aiBubble);
    if (aiBubble.dataset.cursor) {
      aiBubble.querySelector('.cursor-blink').remove();
      delete aiBubble.dataset.cursor;
    }
  } catch (e) {
    aiWrap.classList.add('msg-err');
    aiBubble.textContent = '请求失败：' + e.message;
  }
  box.scrollTop = box.scrollHeight;
}

/* ================= API 配置弹窗 ================= */
function openApiConfig() {
  openModal({
    title: '后端 API 地址配置',
    body: `<div class="form-item"><label class="lbl">API Base URL</label>
      <input id="dlg-api" class="input mono" style="width:100%" value="${esc(API_BASE)}" placeholder="http://localhost:8000"></div>
      <div class="muted mt-8" style="font-size:12px">默认 http://localhost:8000（后端 _run.py 启动）。配置保存在浏览器 localStorage。</div>`,
    footer: `<button class="btn btn-light" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" id="dlg-ok">保存并重连</button>`,
  });
  document.getElementById('dlg-ok').onclick = async () => {
    const v = document.getElementById('dlg-api').value.trim().replace(/\/+$/, '');
    if (!v) { toast('地址不能为空', 'error'); return; }
    API_BASE = v;
    localStorage.setItem(CONFIG_KEY, v);
    closeModal();
    toast('已保存：' + v, 'success');
    healthCheck();
    refreshPage();
  };
}

/* ================= 初始化 ================= */
function init() {
  document.querySelectorAll('.menu-item').forEach((m) => {
    m.addEventListener('click', () => switchPage(m.dataset.page));
  });
  document.getElementById('btn-refresh').addEventListener('click', () => { healthCheck(); refreshPage(); toast('已刷新', 'info', 1200); });
  document.getElementById('btn-api-config').addEventListener('click', openApiConfig);

  // 仪表盘
  document.getElementById('dash-days').addEventListener('change', loadDashboard);
  // 风控检查
  document.getElementById('check-form').addEventListener('submit', (e) => { e.preventDefault(); submitCheck(); });
  // 案件
  document.getElementById('btn-case-search').addEventListener('click', () => { casePage = 1; loadCases(); });
  document.getElementById('btn-auto-close').addEventListener('click', autoCloseCases);
  // 规则
  document.getElementById('rule-filter').addEventListener('change', loadRules);
  document.getElementById('btn-new-rule').addEventListener('click', openNewRule);
  document.getElementById('btn-test-rule').addEventListener('click', openTestRule);
  // 学员
  document.getElementById('btn-query-user').addEventListener('click', queryUserProfile);
  document.getElementById('user-id-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') queryUserProfile(); });
  // 黑名单
  document.getElementById('bl-form').addEventListener('submit', (e) => { e.preventDefault(); addBlacklist(); });
  // 事件
  document.getElementById('btn-event-search').addEventListener('click', () => { eventPage = 1; loadEvents(); });
  // 业务
  document.querySelectorAll('#biz-tabs .tab').forEach((t) => {
    t.addEventListener('click', () => {
      bizType = t.dataset.biz;
      document.querySelectorAll('#biz-tabs .tab').forEach((x) => x.classList.toggle('active', x === t));
      loadBusiness();
    });
  });
  document.getElementById('btn-biz-search').addEventListener('click', loadBusiness);
  // AI
  document.getElementById('btn-agent-send').addEventListener('click', sendAgent);
  document.getElementById('agent-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendAgent(); });

  healthCheck();
  loadDashboard();
}

async function autoCloseCases() {
  if (!confirm('将对待审核且超过超时时间的案件执行自动关闭，继续？')) return;
  try {
    const r = await apiPost('/api/cases/auto-close?hours=24');
    toast(`自动关闭 ${r.closed_count} 个案件`, 'success');
    loadCases();
  } catch (e) { toast(e.message, 'error'); }
}

document.addEventListener('DOMContentLoaded', init);
