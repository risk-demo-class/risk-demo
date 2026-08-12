const App = (() => {
  const escapeHtml = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

  async function api(url, options = {}) {
    const config = { ...options, headers: { ...(options.headers || {}) } };
    if (config.body && !config.headers['Content-Type']) config.headers['Content-Type'] = 'application/json';
    const response = await fetch(url, config);
    const contentType = response.headers.get('content-type') || '';
    let data;
    if (contentType.includes('application/json')) data = await response.json();
    else data = { detail: await response.text() || `HTTP ${response.status}` };
    if (!response.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map(item => item.msg || JSON.stringify(item)).join('；')
        : (data.detail || data.message || `请求失败（${response.status}）`);
      throw new Error(detail);
    }
    return data;
  }

  function formatDate(value) {
    if (!value) return '-';
    const raw = /Z|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
    const date = new Date(raw);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
  }

  function badge(value) {
    const map = {
      '低':'low','中':'medium','高':'high','极高':'extreme',
      '通过':'pass','标记':'flag','人工审核':'review','拒绝':'reject',
      '待审核':'pending','审核中':'reviewing','已通过':'approved','已拒绝':'rejected','已关闭':'closed',
      true:'enabled',false:'disabled'
    };
    const label = typeof value === 'boolean' ? (value ? '启用' : '停用') : value;
    return `<span class="badge badge-${map[value] || 'disabled'}">${escapeHtml(label)}</span>`;
  }

  function toast(message, error = false) {
    let element = document.getElementById('app-toast');
    if (!element) {
      element = document.createElement('div'); element.id = 'app-toast'; element.className = 'toast';
      document.body.appendChild(element);
    }
    element.textContent = message; element.className = `toast show${error ? ' error' : ''}`;
    clearTimeout(element._timer);
    element._timer = setTimeout(() => element.classList.remove('show'), 3000);
  }

  function openModal(id) { document.getElementById(id)?.classList.add('show'); }
  function closeModal(id) { document.getElementById(id)?.classList.remove('show'); }
  function pretty(value) { return JSON.stringify(value, null, 2); }
  function query(params) {
    const result = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) result.set(key, value);
    });
    return result.toString();
  }
  function pageControls(container, { page, pageSize, total, onPage }) {
    const pages = Math.max(1, Math.ceil(total / pageSize));
    container.innerHTML = `
      <span>共 ${total} 条，第 ${page}/${pages} 页</span>
      <button class="btn btn-secondary btn-sm" ${page <= 1 ? 'disabled' : ''} data-page="${page-1}">上一页</button>
      <button class="btn btn-secondary btn-sm" ${page >= pages ? 'disabled' : ''} data-page="${page+1}">下一页</button>`;
    container.querySelectorAll('[data-page]').forEach(btn => btn.onclick = () => onPage(Number(btn.dataset.page)));
  }
  document.addEventListener('click', event => {
    if (event.target.classList.contains('modal-backdrop')) event.target.classList.remove('show');
    const closer = event.target.closest('[data-close-modal]');
    if (closer) closeModal(closer.dataset.closeModal);
  });
  return { api, escapeHtml, formatDate, badge, toast, openModal, closeModal, pretty, query, pageControls };
})();
