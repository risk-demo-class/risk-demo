function showToast(message) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2600);
}

async function updateEventStatus(id, status) {
  const response = await fetch(`/api/risk-events/${id}/status`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({handled_status: status}),
  });
  if (!response.ok) throw new Error((await response.json()).detail || '更新失败');
  return response.json();
}

async function updateCaseStatus(id, status) {
  const response = await fetch(`/api/cases/${id}/status`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status}),
  });
  if (!response.ok) throw new Error((await response.json()).detail || '更新失败');
  return response.json();
}

function bindStatusActions(selector, updater, successMessage) {
  document.querySelectorAll(selector).forEach((select) => select.addEventListener('change', async (event) => {
    const status = event.target.value;
    if (!status) return;
    const id = event.target.dataset.eventId || event.target.dataset.caseId;
    try {
      await updater(id, status);
      showToast(successMessage);
      setTimeout(() => location.reload(), 450);
    } catch (error) {
      showToast(error.message);
    } finally {
      event.target.value = '';
    }
  }));
}

bindStatusActions('.event-action', updateEventStatus, '风险事件状态已更新');
bindStatusActions('.case-action', updateCaseStatus, '风险案件状态已更新');

const filterButton = document.getElementById('filterEvents');
if (filterButton) {
  filterButton.addEventListener('click', async () => {
    const params = new URLSearchParams();
    const status = document.getElementById('statusFilter').value;
    const decision = document.getElementById('decisionFilter').value;
    if (status) params.set('status', status);
    if (decision) params.set('decision', decision);
    const response = await fetch(`/api/risk-events?${params}`);
    const {items} = await response.json();
    const table = document.getElementById('eventsTable');
    table.innerHTML = items.map((event) => `<tr><td><b>${event.entity_id}</b><small>${event.reason || ''}</small></td><td><b>${event.rule_id || ''}</b><small>${event.rule_name || ''}</small></td><td><strong class="risk-score">${event.risk_score}</strong></td><td><span class="decision decision-${event.decision.toLowerCase()}">${event.decision}</span></td><td><span class="badge badge-${event.handled_status.toLowerCase()}">${event.handled_status}</span></td><td>${event.event_at}</td><td><select class="event-action" data-event-id="${event.risk_event_id}"><option value="">更新状态</option><option value="ACKED">确认处理</option><option value="CLOSED">关闭事件</option><option value="OPEN">重新打开</option></select></td></tr>`).join('');
    bindStatusActions('.event-action', updateEventStatus, '风险事件状态已更新');
  });
}

const modal = document.getElementById('assessmentModal');
document.querySelectorAll('.assess-button').forEach((button) => button.addEventListener('click', async () => {
  try {
    button.textContent = '评估中…';
    button.disabled = true;
    const response = await fetch(`/api/work-orders/${button.dataset.workOrderId}/assess`, {method: 'POST'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '评估失败');

    document.getElementById('assessmentTitle').textContent = `${result.source_id} 联合风险评估`;
    document.getElementById('assessmentScore').textContent = result.final_score;
    document.getElementById('assessmentDecision').innerHTML = `<span class="decision decision-${result.decision.toLowerCase()}">${result.decision}</span>`;
    document.getElementById('assessmentProbability').textContent = `规则分：${result.rule_score} · XGBoost 模型分：${result.ml_score ?? '未加载'} · 命中规则：${result.rule_hits.length} 条`;
    document.getElementById('assessmentCase').textContent = result.case_id ? `已自动建案：${result.case_id}` : '未触发自动建案';
    document.getElementById('assessmentRules').innerHTML = result.rule_hits.length
      ? result.rule_hits.map((hit) => `<li><b>${hit.rule_id} · ${hit.rule_name}</b><span>${hit.reason}</span></li>`).join('')
      : '<li><span>未命中硬性业务规则。</span></li>';
    document.getElementById('assessmentFeatures').innerHTML = Object.entries(result.features)
      .map(([key, value]) => `<div class="feature-item"><span>${key}</span><b>${Number(value).toFixed(4)}</b></div>`).join('');
    modal.classList.add('show');
  } catch (error) {
    showToast(error.message);
  } finally {
    button.textContent = '评估';
    button.disabled = false;
  }
}));

if (modal) {
  document.getElementById('closeAssessment').addEventListener('click', () => modal.classList.remove('show'));
  modal.addEventListener('click', (event) => {
    if (event.target === modal) modal.classList.remove('show');
  });
}
const businessConfig = {
  supplier: {label: '供应商', id: 'supplier_id', columns: ['supplier_id', 'supplier_name', 'supplier_level', 'qualification_status', 'qualification_expire_at', 'risk_level'], editable: ['qualification_status', 'qualification_expire_at', 'risk_level'], options: {qualification_status: ['VALID', 'EXPIRED', 'SUSPENDED'], risk_level: ['LOW', 'MEDIUM', 'HIGH']}},
  equipment: {label: '设备', id: 'equipment_id', columns: ['equipment_id', 'equipment_name', 'equipment_type', 'criticality', 'status', 'maintenance_due_at', 'calibration_due_at'], editable: ['status', 'maintenance_due_at', 'calibration_due_at'], options: {status: ['RUNNING', 'ALARM', 'STOPPED', 'MAINTENANCE']}},
  work_order: {label: '工单', id: 'work_order_id', columns: ['work_order_id', 'material_name', 'planned_qty', 'completed_qty', 'status', 'planned_end_at'], editable: ['planned_qty', 'completed_qty', 'status'], options: {status: ['PLANNED', 'IN_PROGRESS', 'HOLD', 'COMPLETED']}},
  ipqc_inspection: {label: '过程质检', id: 'ipqc_id', columns: ['ipqc_id', 'work_order_id', 'equipment_id', 'measured_value', 'lsl', 'usl', 'result', 'inspected_at'], editable: ['measured_value', 'result'], options: {result: ['PASSED', 'FAILED', 'HOLD']}},
  shipment: {label: '发运', id: 'shipment_id', columns: ['shipment_id', 'sales_order_id', 'ship_qty', 'quality_status', 'released_by', 'ship_at'], editable: ['quality_status', 'released_by'], options: {quality_status: ['PASSED', 'HOLD', 'FAILED']}},
};

const managementTabs = document.getElementById('managementTabs');
if (managementTabs) {
  const managementModal = document.getElementById('businessEditModal');
  let managementData = {};
  let activeEntity = 'supplier';
  let editingRecord = null;

  const displayValue = (value) => value === null || value === undefined ? '-' : String(value);
  const humanize = (field) => ({supplier_id: '供应商编号', supplier_name: '供应商名称', supplier_level: '供应商等级', qualification_status: '资质状态', qualification_expire_at: '资质到期日', risk_level: '风险等级', equipment_id: '设备编号', equipment_name: '设备名称', equipment_type: '设备类型', criticality: '关键等级', status: '状态', maintenance_due_at: '保养到期日', calibration_due_at: '校准到期日', work_order_id: '工单编号', material_name: '产品', planned_qty: '计划数量', completed_qty: '完工数量', planned_end_at: '计划结束', ipqc_id: '质检编号', measured_value: '实测值', lsl: '下限', usl: '上限', result: '检验结果', inspected_at: '检验时间', shipment_id: '发运编号', sales_order_id: '销售订单', ship_qty: '发运数量', quality_status: '放行质量', released_by: '放行人', ship_at: '发运时间'})[field] || field;

  function renderManagement() {
    const config = businessConfig[activeEntity];
    document.getElementById('managementHead').innerHTML = `<tr>${config.columns.map((column) => `<th>${humanize(column)}</th>`).join('')}<th>操作</th></tr>`;
    document.getElementById('managementBody').innerHTML = (managementData[activeEntity] || []).map((record) => `<tr>${config.columns.map((column) => `<td>${displayValue(record[column])}</td>`).join('')}<td><button class="secondary-button edit-business-record" data-id="${record[config.id]}">编辑</button></td></tr>`).join('');
    document.querySelectorAll('.edit-business-record').forEach((button) => button.addEventListener('click', () => openBusinessEditor(button.dataset.id)));
  }

  function inputFor(field, value, config) {
    if (config.options[field]) return `<select name="${field}">${config.options[field].map((option) => `<option value="${option}" ${String(value) === option ? 'selected' : ''}>${option}</option>`).join('')}</select>`;
    const inputType = field.endsWith('_at') ? 'date' : (field.endsWith('_qty') || field === 'measured_value' ? 'number' : 'text');
    const step = field === 'measured_value' ? '0.0001' : '1';
    const normalized = inputType === 'date' && value ? String(value).slice(0, 10) : displayValue(value === null ? '' : value);
    return `<input name="${field}" type="${inputType}" step="${step}" value="${normalized === '-' ? '' : normalized}" required>`;
  }

  function openBusinessEditor(recordId) {
    const config = businessConfig[activeEntity];
    editingRecord = (managementData[activeEntity] || []).find((record) => String(record[config.id]) === recordId);
    if (!editingRecord) return;
    document.getElementById('businessEditTitle').textContent = `编辑${config.label}：${recordId}`;
    document.getElementById('businessEditForm').innerHTML = config.editable.map((field) => `<label>${humanize(field)}${inputFor(field, editingRecord[field], config)}</label>`).join('');
    managementModal.classList.add('show');
  }

  async function loadBusinessData() {
    const response = await fetch('/api/business-data');
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '加载业务数据失败');
    managementData = result.items;
    renderManagement();
  }

  managementTabs.querySelectorAll('button').forEach((button) => button.addEventListener('click', () => {
    activeEntity = button.dataset.entity;
    managementTabs.querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
    renderManagement();
  }));
  document.getElementById('closeBusinessEdit').addEventListener('click', () => managementModal.classList.remove('show'));
  document.getElementById('cancelBusinessEdit').addEventListener('click', () => managementModal.classList.remove('show'));
  document.getElementById('businessEditForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const config = businessConfig[activeEntity];
    const formData = new FormData(event.target);
    const changes = Object.fromEntries(config.editable.map((field) => [field, formData.get(field)]));
    for (const field of ['planned_qty', 'completed_qty', 'measured_value']) if (field in changes) changes[field] = Number(changes[field]);
    try {
      const response = await fetch(`/api/business-data/${activeEntity}/${editingRecord[config.id]}`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({changes, recheck: document.getElementById('businessRecheck').checked})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || '保存失败');
      managementModal.classList.remove('show');
      showToast(result.assessments.length ? `已保存，并重新评估 ${result.assessments.length} 个工单` : '业务数据已保存');
      await loadBusinessData();
    } catch (error) {
      showToast(error.message);
    }
  });
  managementModal.addEventListener('click', (event) => { if (event.target === managementModal) managementModal.classList.remove('show'); });
  loadBusinessData().catch((error) => showToast(error.message));
}