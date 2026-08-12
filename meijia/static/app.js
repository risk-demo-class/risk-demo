const $ = (s) => document.querySelector(s);
const fmt = (v) => v == null ? "—" : new Intl.NumberFormat("zh-CN").format(v);
const dt = (v) => v ? new Date(v).toLocaleString("zh-CN", {hour12:false}) : "—";
const badge = (v) => `<span class="badge ${v}">${v || "—"}</span>`;

async function api(path, options={}) {
  const response = await fetch(path, {headers:{"Content-Type":"application/json", ...(options.headers||{})}, ...options});
  if (!response.ok) {
    let msg = `请求失败 ${response.status}`;
    try { const body = await response.json(); msg = body.detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return response.status === 204 ? null : response.json();
}
function toast(message, error=false) { const node=$("#toast"); node.textContent=message; node.className=`toast show ${error?"error":""}`; setTimeout(()=>node.className="toast",2500); }
function formJSON(form) { const data=Object.fromEntries(new FormData(form)); Object.keys(data).forEach(k=>{if(data[k]==="")data[k]=null}); return data; }

async function initShell(){
  const tick=()=>{const n=$("#clock");if(n)n.textContent=new Date().toLocaleString("zh-CN",{hour12:false})};tick();setInterval(tick,1000);
  try{await api("/api/health");$("#health").textContent="服务正常"}catch(e){$("#health").textContent="服务异常";$("#health").classList.add("bad")}
}

async function loadDashboard(){
  const d=await api("/api/dashboard/overview");
  $("#metrics").innerHTML=[
    ["累计评估",fmt(d.assessment_count),"全部业务风险事件"],
    ["风险事件",fmt(d.risk_count),`风险率 ${(d.risk_rate*100).toFixed(1)}%`],
    ["待审案件",fmt(d.pending_cases),"等待人工处置"],
    ["账号规模",fmt(d.user_count),"学生 / 家长 / 老师"],
  ].map(x=>`<div class="metric"><span>${x[0]}</span><strong>${x[1]}</strong><small>${x[2]}</small></div>`).join("");
  const max=Math.max(...Object.values(d.decision_distribution),1);
  $("#decisionChart").innerHTML=["通过","标记","人工审核","拒绝"].map(k=>`<div class="bar-row"><span>${k}</span><div class="bar-track"><div class="bar-fill" style="width:${100*(d.decision_distribution[k]||0)/max}%"></div></div><strong>${d.decision_distribution[k]||0}</strong></div>`).join("");
  $("#recent").innerHTML=d.recent.map(x=>`<div class="feed-item"><div><strong>${x.user_id}</strong><small>${x.assessment_id} · ${dt(x.created_at)}</small></div><div>${badge(x.decision)} <b>${x.final_score}</b></div></div>`).join("")||'<div class="empty">暂无评估</div>';
}

function bindRiskCheck(){
  $("#riskForm").addEventListener("submit",async e=>{e.preventDefault();const out=$("#checkResult");out.innerHTML="正在计算 25 维特征…";
    try{const d=await api("/api/risk/check",{method:"POST",body:JSON.stringify(formJSON(e.target))});out.innerHTML=`<div class="score-ring" style="--score:${d.final_score}"><strong>${d.final_score}</strong></div><div class="result-title"><h2>${d.decision}</h2><p>${badge(d.risk_level)} · 命中 ${d.rule_count} 条规则</p><small>${d.assessment_id}</small></div><div class="hit-list">${d.triggered_rules.map(r=>`<div class="hit"><span><b>${r.rule_id}</b> ${r.rule_name}</span>${badge(r.action)}</div>`).join("")||'<div class="empty">未命中风险规则</div>'}</div>`;toast("风险检查已完成")}
    catch(err){out.innerHTML=`<div class="empty">${err.message}</div>`;toast(err.message,true)}});
}

let ruleCache={};
async function loadRules(){
  const d=await api("/api/rules");ruleCache=Object.fromEntries(d.items.map(r=>[r.rule_id,r]));$("#ruleRows").innerHTML=d.items.map(r=>`<tr><td><b>${r.rule_id}</b></td><td>${r.rule_name}</td><td>${r.event_type}</td><td><code>${JSON.stringify(r.condition)}</code></td><td>${badge(r.risk_level)}</td><td>${r.risk_score}</td><td>${badge(r.action)}</td><td>v${r.version}</td><td><button class="switch ${r.enabled?"on":""}" aria-label="切换规则" onclick="toggleRule('${r.rule_id}')"></button></td><td><button class="btn" onclick="openRule('${r.rule_id}')">编辑</button></td></tr>`).join("");
}
async function toggleRule(id){try{await api(`/api/rules/${id}/toggle`,{method:"PUT"});await loadRules();toast(`${id} 状态已更新`)}catch(e){toast(e.message,true)}}
function openRule(id){const r=ruleCache[id],f=$("#ruleForm");f.rule_id.value=id;f.version.value=r.version;f.risk_level.value=r.risk_level;f.risk_score.value=r.risk_score;f.action.value=r.action;f.priority.value=r.priority;f.rule_condition.value=JSON.stringify(r.condition,null,2);$("#ruleDialog").showModal()}
function bindRuleEdit(){$("#ruleForm").addEventListener("submit",async e=>{e.preventDefault();const f=e.target;let condition;try{condition=JSON.parse(f.rule_condition.value)}catch(_){toast("JSON 条件格式错误",true);return}const body={version:Number(f.version.value),risk_level:f.risk_level.value,risk_score:Number(f.risk_score.value),action:f.action.value,priority:Number(f.priority.value),rule_condition:condition};try{await api(`/api/rules/${f.rule_id.value}`,{method:"PUT",body:JSON.stringify(body)});$("#ruleDialog").close();await loadRules();toast("规则新版本已生效")}catch(err){toast(err.message,true)}})}

async function loadAssessments(){
  const p=new URLSearchParams({page_size:"50"});if($("#assessmentUser")?.value)p.set("user_id",$("#assessmentUser").value);if($("#assessmentDecision")?.value)p.set("decision",$("#assessmentDecision").value);
  const d=await api(`/api/assessments?${p}`);$("#assessmentRows").innerHTML=d.items.map(x=>`<tr class="clickable" onclick="showAssessment('${x.assessment_id}')"><td>${x.assessment_id}</td><td>${x.user_id}</td><td><b>${x.final_score}</b></td><td>${badge(x.risk_level)}</td><td>${badge(x.decision)}</td><td>${x.rule_count}</td><td>${dt(x.created_at)}</td></tr>`).join("");
}
async function showAssessment(id){const d=await api(`/api/assessments/${id}`);$("#assessmentDetail").innerHTML=`<p class="eyebrow">ASSESSMENT DETAIL</p><h2>${id}</h2><p>${badge(d.decision)} ${badge(d.risk_level)}　得分 <b>${d.final_score}</b></p><h3>命中规则</h3><div class="hit-list">${d.triggered_rules.map(r=>`<div class="hit"><span>${r.rule_id} ${r.rule_name}</span>${badge(r.action)}</div>`).join("")||"无"}</div><h3>特征快照</h3><div class="json-grid">${Object.entries(d.features).map(([k,v])=>`<div class="json-item"><small>${k}</small><br><b>${v}</b></div>`).join("")}</div>`;$("#assessmentDialog").showModal()}

async function loadCases(){
  const status=$("#caseStatus")?.value||"";const [stats,d]=await Promise.all([api("/api/cases/statistics"),api(`/api/cases?page_size=50&status=${encodeURIComponent(status)}`)]);
  const values=stats.by_status;$("#caseMetrics").innerHTML=["待审核","审核中","已通过","已拒绝","已关闭"].map(k=>`<div class="metric"><span>${k}</span><strong>${values[k]||0}</strong></div>`).join("");
  $("#caseRows").innerHTML=d.items.map(x=>`<tr><td>${x.case_id}</td><td>${x.user_id}</td><td>${x.case_category}</td><td>${x.final_score} ${badge(x.risk_level)}</td><td>${badge(x.case_status)}</td><td>${dt(x.created_at)}</td><td>${["待审核","审核中"].includes(x.case_status)?`<button class="btn" onclick="openReview('${x.case_id}')">审核</button>`:"—"}</td></tr>`).join("");
}
function openReview(id){$("#reviewForm [name=case_id]").value=id;$("#reviewDialog").showModal()}
function bindReview(){$("#reviewForm").addEventListener("submit",async e=>{e.preventDefault();const d=formJSON(e.target),id=d.case_id;delete d.case_id;try{await api(`/api/cases/${id}/review`,{method:"POST",body:JSON.stringify(d)});$("#reviewDialog").close();loadCases();toast("案件审核完成")}catch(err){toast(err.message,true)}})}

async function loadBlacklist(){const d=await api("/api/blacklist?page_size=100");$("#blacklistRows").innerHTML=d.items.map(x=>`<tr><td>${x.type}</td><td><code>${x.value}</code></td><td>${x.reason}</td><td>${badge(x.status)}</td><td><button class="btn" onclick="removeBlacklist(${x.entry_id})">移除</button></td></tr>`).join("")}
async function removeBlacklist(id){if(!confirm("确认移除该黑名单记录？"))return;try{await api(`/api/blacklist/${id}`,{method:"DELETE"});loadBlacklist();toast("已移除")}catch(e){toast(e.message,true)}}
function bindBlacklist(){$("#blacklistForm").addEventListener("submit",async e=>{e.preventDefault();try{await api("/api/blacklist",{method:"POST",body:JSON.stringify(formJSON(e.target))});e.target.reset();loadBlacklist();toast("已加入黑名单")}catch(err){toast(err.message,true)}})}

async function loadUsers(){const q=$("#userSearch")?.value||"";const d=await api(`/api/users?limit=100&q=${encodeURIComponent(q)}`);$("#userRows").innerHTML=d.items.map(x=>`<div class="user-item" onclick="showUser('${x.user_id}',this)"><div><b>${x.name}</b><small>${x.user_id} · ${x.student_id||"无学号"}</small></div>${badge(x.role)}</div>`).join("")}
async function showUser(id,node){document.querySelectorAll(".user-item").forEach(x=>x.classList.remove("active"));node?.classList.add("active");const d=await api(`/api/users/${id}/profile`),u=d.user,m=d.metrics;$("#userProfile").innerHTML=`<div class="profile-head"><div class="avatar">${u.name.slice(0,1)}</div><div><h2>${u.name}</h2><p>${u.user_id} · ${u.student_id||"无学号"} · ${badge(u.real_name_status)}</p></div></div><div class="profile-grid">${[["账号年龄",m.account_age_days.toFixed(0)+" 天"],["近180天设备",m.device_count_180d],["同设备学员",m.device_student_count],["订单数",m.orders],["成功退款",m.successful_refunds],["黑名单命中",m.student_blacklist_hit?"是":"否"]].map(x=>`<div class="profile-stat"><span>${x[0]}</span><strong>${x[1]}</strong></div>`).join("")}</div><h3>最近评估</h3>${d.latest_assessment?`<div class="hit"><span>${d.latest_assessment.assessment_id}</span><span>${badge(d.latest_assessment.decision)} ${d.latest_assessment.final_score}分</span></div>`:'<p class="muted">暂无评估记录</p>'}`}

function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
async function sendChat(){
  const box=$("#chatInput"), out=$("#chatMessages"), msg=box.value.trim(); if(!msg)return;
  box.value="";
  out.insertAdjacentHTML("beforeend",`<div class="msg user"><b>我</b><p>${escapeHtml(msg)}</p></div>`);
  out.insertAdjacentHTML("beforeend",`<div class="msg bot typing"><b>AI 助手</b><p>…</p></div>`);
  out.scrollTop=out.scrollHeight;
  const removeTyping=()=>{const t=out.querySelector(".typing");if(t)t.remove()};
  try{
    const d=await api("/api/agent/chat",{method:"POST",body:JSON.stringify({message:msg})});
    removeTyping();
    out.insertAdjacentHTML("beforeend",`<div class="msg bot"><b>AI 助手</b><p>${escapeHtml(d.reply)}</p></div>`);
  }catch(e){
    removeTyping();
    out.insertAdjacentHTML("beforeend",`<div class="msg bot error"><b>AI 助手</b><p>${escapeHtml(e.message)}</p></div>`);
  }
  out.scrollTop=out.scrollHeight;
}
function bindChat(){
  $("#chatSend").addEventListener("click",sendChat);
  $("#chatInput").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();sendChat()}});
}

document.addEventListener("DOMContentLoaded",async()=>{initShell();const p=document.body.dataset.page;try{if(p==="dashboard")await loadDashboard();if(p==="risk-check")bindRiskCheck();if(p==="rules"){await loadRules();bindRuleEdit()}if(p==="assessments")await loadAssessments();if(p==="cases"){await loadCases();bindReview()}if(p==="blacklist"){await loadBlacklist();bindBlacklist()}if(p==="users")await loadUsers();if(p==="chat")bindChat()}catch(e){toast(e.message,true)}});
