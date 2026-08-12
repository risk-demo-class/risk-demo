/* ============================================================
   core.js — API 客户端 + 通用组件 + SVG 图表（零外部依赖）
   ============================================================ */
'use strict';

/* ---------------- API 客户端 ---------------- */
const CONFIG_KEY = 'edurisk_api_base';
let API_BASE = localStorage.getItem(CONFIG_KEY) || 'http://localhost:8000';

async function api(path, options = {}) {
  const { body, ...rest } = options;
  const res = await fetch(API_BASE + path, {
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    ...rest,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = 'HTTP ' + res.status;
    try {
      const j = await res.json();
      detail = j.detail || (typeof j === 'string' ? j : JSON.stringify(j));
    } catch (e) { /* ignore */ }
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

const apiGet = (p) => api(p);
const apiPost = (p, body) => api(p, { method: 'POST', body });
const apiPatch = (p, body) => api(p, { method: 'PATCH', body });

/* ---------------- 工具函数 ---------------- */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
function fmtNum(n) { return Number(n ?? 0).toLocaleString('zh-CN'); }
function fmtMoney(n) { return '¥' + Number(n ?? 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 }); }
function fmtTime(t) {
  if (!t) return '—';
  return String(t).replace('T', ' ').slice(0, 19);
}
function parseExtra(text) {
  const s = (text || '').trim();
  if (!s) return {};
  const obj = JSON.parse(s);           // 抛错由调用方捕获
  if (typeof obj !== 'object' || Array.isArray(obj)) throw new Error('extra 必须是 JSON 对象');
  return obj;
}

/* 决策/风险等级 → 徽章 class */
const DECISION_CLASS = { '通过': 'badge-green', '标记': 'badge-blue', '人工审核': 'badge-orange', '拒绝': 'badge-red' };
const LEVEL_CLASS = { '低': 'badge-green', '中': 'badge-gold', '高': 'badge-orange', '极高': 'badge-red' };
const LEVEL_COLOR = { '低': '#16a34a', '中': '#f59e0b', '高': '#ea580c', '极高': '#dc2626' };
const CASE_STATUS_CLASS = {
  '待审核': 'badge-orange', '审核中': 'badge-blue',
  '已通过': 'badge-green', '已拒绝': 'badge-red', '已关闭': 'badge-gray',
};

/* ---------------- Toast ---------------- */
let _toastTimer = null;
function toast(msg, type = 'info', ms = 2600) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast ' + type;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add('hidden'), ms);
}

/* ---------------- Modal ---------------- */
function openModal({ title, body, footer, wide }) {
  document.getElementById('modal-title').textContent = title;
  const m = document.getElementById('modal-mask');
  m.querySelector('.modal').classList.toggle('modal-lg', !!wide);
  document.getElementById('modal-body').innerHTML = body;
  const foot = document.getElementById('modal-foot');
  foot.innerHTML = footer || '';
  m.classList.remove('hidden');
}
function closeModal() { document.getElementById('modal-mask').classList.add('hidden'); }
document.getElementById('modal-close').addEventListener('click', closeModal);
document.getElementById('modal-mask').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeModal();
});

/* ---------------- SVG 图表 ---------------- */
/* 折线图：data = [{label, value}] */
function svgLineChart(el, data, { color = '#2563eb', height = 240 } = {}) {
  const W = 620, H = height;
  if (!data || !data.length) { el.innerHTML = '<div class="empty">暂无数据</div>'; return; }
  const padL = 34, padR = 14, padT = 16, padB = 30;
  const iw = W - padL - padR, ih = H - padT - padB;
  const vals = data.map((d) => d.value);
  const maxV = Math.max(1, ...vals) * 1.15;
  const px = (i) => padL + (data.length === 1 ? iw / 2 : (i / (data.length - 1)) * iw);
  const py = (v) => padT + ih - (v / maxV) * ih;
  const pts = data.map((d, i) => `${px(i).toFixed(1)},${py(d.value).toFixed(1)}`);

  let grid = '';
  for (let g = 0; g <= 4; g++) {
    const y = padT + (ih / 4) * g;
    const lv = Math.round(maxV * (1 - g / 4));
    grid += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#e8ecf3" stroke-width="1"/>
      <text x="${padL - 8}" y="${y + 4}" font-size="10" fill="#94a3b8" text-anchor="end">${lv}</text>`;
  }
  let line = '', dots = '', labels = '';
  data.forEach((d, i) => {
    dots += `<circle cx="${px(i)}" cy="${py(d.value)}" r="3.2" fill="${color}">
      <title>${esc(d.label)}: ${fmtNum(d.value)}</title></circle>`;
    if (data.length <= 12 || i % Math.ceil(data.length / 12) === 0 || i === data.length - 1) {
      labels += `<text x="${px(i)}" y="${H - 8}" font-size="10" fill="#94a3b8" text-anchor="middle">${esc(d.label)}</text>`;
    }
  });

  el.innerHTML = `
  <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto" role="img">
    <defs>
      <linearGradient id="lg-line" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${color}" stop-opacity="0.18"/>
        <stop offset="100%" stop-color="${color}" stop-opacity="0.01"/>
      </linearGradient>
    </defs>
    ${grid}
    <polygon points="${pts.join(' ')} ${px(data.length - 1)},${py(0)} ${px(0)},${py(0)}" fill="url(#lg-line)"/>
    <polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    ${dots}${labels}
  </svg>`;
}

/* 环形图：data = [{label, value, color}]，可带中心文字 */
function svgDonut(el, data, { center, size = 220, thickness = 30 } = {}) {
  if (!data || !data.length) { el.innerHTML = '<div class="empty">暂无数据</div>'; return; }
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const R = (size - thickness) / 2, C = size / 2;
  const circ = 2 * Math.PI * R;
  let acc = 0, segs = '';
  data.forEach((d) => {
    const frac = d.value / total;
    const len = frac * circ;
    const off = acc * circ;
    if (d.value > 0) {
      segs += `<circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="${d.color}" stroke-width="${thickness}"
        stroke-dasharray="${len.toFixed(2)} ${(circ - len).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}"
        transform="rotate(-90 ${C} ${C})">
        <title>${esc(d.label)}: ${fmtNum(d.value)} (${(frac * 100).toFixed(1)}%)</title></circle>`;
    }
    acc += frac;
  });
  el.innerHTML = `
  <div style="display:flex;align-items:center;gap:22px;flex-wrap:wrap;justify-content:center">
    <svg viewBox="0 0 ${size} ${size}" style="width:${size}px;height:${size}px;flex-shrink:0">
      <circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="#eef1f5" stroke-width="${thickness}"/>
      ${segs}
      <text x="${C}" y="${C - 4}" text-anchor="middle" font-size="15" font-weight="800" fill="#1f2937">${esc(center || '')}</text>
      <text x="${C}" y="${C + 16}" text-anchor="middle" font-size="10" fill="#94a3b8">总数 ${fmtNum(total)}</text>
    </svg>
    <div class="legend">${data.map((d) => `
      <div class="lg-item"><span class="lg-dot" style="background:${d.color}"></span>${esc(d.label)}
        <b>${fmtNum(d.value)}</b><span class="lg-pct">${(d.value / total * 100).toFixed(1)}%</span></div>`).join('')}
    </div>
  </div>`;
}

/* 横向条形图：items = [{label, value, sub}] */
function svgBars(el, items, { color = '#2563eb', height = 260 } = {}) {
  if (!items || !items.length) { el.innerHTML = '<div class="empty">暂无数据</div>'; return; }
  const rowH = 26, padT = 4, padB = 6;
  const H = Math.max(90, padT + padB + items.length * rowH);
  const W = 660;
  const maxV = Math.max(1, ...items.map((d) => d.value)) * 1.12;
  const barMaxW = W - 150;
  const rows = items.map((d, i) => {
    const y = padT + i * rowH;
    const bw = Math.max(2, (d.value / maxV) * barMaxW);
    const pct = d.sub !== undefined ? ` ${(d.sub * 100).toFixed(1)}%` : '';
    return `
      <text x="4" y="${y + 14}" font-size="11.5" fill="#475569">${esc(d.label)}</text>
      <rect x="92" y="${y + 3}" rx="5" width="${bw.toFixed(1)}" height="15" fill="${color}" opacity="0.9">
        <title>${esc(d.label)}: ${fmtNum(d.value)}${pct}</title></rect>
      <text x="${(92 + bw + 6).toFixed(1)}" y="${y + 15}" font-size="11" font-weight="700" fill="#1f2937">${fmtNum(d.value)}${pct}</text>`;
  }).join('');
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto" role="img">${rows}</svg>`;
}

/* ---------------- 通用表格渲染辅助 ---------------- */
function renderPagination(container, { page, pageSize, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  let html = `<span class="pg-info">共 ${fmtNum(total)} 条 · 第 ${page}/${pages} 页</span>`;
  html += `<button class="pg-btn" data-p="${page - 1}" ${page <= 1 ? 'disabled' : ''}>上一页</button>`;
  const from = Math.max(1, page - 2), to = Math.min(pages, page + 2);
  for (let p = from; p <= to; p++) {
    html += `<button class="pg-btn ${p === page ? 'active' : ''}" data-p="${p}">${p}</button>`;
  }
  html += `<button class="pg-btn" data-p="${page + 1}" ${page >= pages ? 'disabled' : ''}>下一页</button>`;
  container.innerHTML = html;
  container.querySelectorAll('.pg-btn[data-p]').forEach((b) => {
    b.addEventListener('click', () => {
      const p = parseInt(b.dataset.p, 10);
      if (p >= 1 && p <= pages && p !== page) onChange(p);
    });
  });
}

/* 空表格提示 */
function emptyRow(colspan, text = '暂无数据') {
  return `<tr><td colspan="${colspan}" style="text-align:center;color:#94a3b8;padding:36px 0">${text}</td></tr>`;
}

/* 键值详情表 */
function detailTable(rows) {
  return `<table class="detail-table">${rows.map(([k, v]) =>
    `<tr><th>${esc(k)}</th><td>${v === null || v === undefined ? '—' : esc(v)}</td></tr>`).join('')}</table>`;
}

/* 特性 JSON 块 */
function jsonBlock(obj) {
  return `<pre class="json-block">${esc(JSON.stringify(obj, null, 2))}</pre>`;
}
