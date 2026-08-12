const q = (selector) => document.querySelector(selector);
async function api(url, options={}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json',...(options.headers||{})}, ...options});
  if (response.status === 401) {
    location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
    throw new Error('登录状态已失效，请重新登录');
  }
  if (!response.ok) { let detail=`请求失败 (${response.status})`; try { const body=await response.json(); detail=body.detail||detail; } catch(_){} throw new Error(detail); }
  return response.json();
}
function toast(message, bad=false){const box=q('#toast');box.textContent=message;box.className=`toast show ${bad?'bad':''}`;setTimeout(()=>box.classList.remove('show'),2600)}
function showError(error){console.error(error);toast(error.message||'操作失败',true)}
function fmt(value){return value===null||value===undefined?'—':Number(value).toFixed(3)}
function dateTime(value){return value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'—'}
function levelClass(level){return ({'低':'low','中':'medium','高':'high','极高':'critical'})[level]||''}
function decisionClass(value){return ({'通过':'pass','已通过':'pass','标记':'medium','人工审核':'high','待审核':'high','审核中':'medium','拒绝':'critical','已拒绝':'critical'})[value]||''}
function escapeHtml(value){const div=document.createElement('div');div.textContent=value;return div.innerHTML}
