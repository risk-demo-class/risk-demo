/**
 * 银行风控系统 - 公共前端工具函数
 * ================================
 * 共享的 API 请求、风险等级展示、分页等工具。
 */

// 风险等级 → Badge 样式
function getRiskBadgeClass(level) {
    const map = {
        '低':   'badge-risk-low',
        '中':   'badge-risk-mid',
        '高':   'badge-risk-high',
        '极高': 'badge-risk-critical',
    };
    return map[level] || 'bg-secondary';
}

// 决策 → Badge 样式
function getDecisionBadge(decision) {
    const map = {
        'PASS':      '<span class="badge badge-decision-pass">✓ 通过</span>',
        'CHALLENGE': '<span class="badge badge-decision-challenge">⚠ 增强验证</span>',
        'MANUAL':    '<span class="badge badge-decision-manual">⏳ 人工复核</span>',
        'REJECT':    '<span class="badge badge-decision-reject">✕ 拒绝</span>',
    };
    return map[decision] || `<span class="badge bg-secondary">${decision}</span>`;
}

// 通用 API 请求封装
async function apiRequest(url, options = {}) {
    const defaultOptions = { headers: { 'Content-Type': 'application/json' } };
    const res = await fetch(url, { ...defaultOptions, ...options });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '请求失败' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

// ML P(拒绝) → 0-100 风险分 (sigmoid 校准)
function mlProbToRiskScore(prob, k = 3) {
    if (prob == null || isNaN(prob)) return null;
    if (prob <= 0) return 0;
    if (prob >= 1) return 100;
    return Math.round(100 * (1 - Math.exp(-k * prob)));
}

// 格式化金额
function fmtAmount(val) {
    if (val == null) return '-';
    return '¥' + Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// 格式化时间
function fmtTime(val) {
    if (!val) return '-';
    return new Date(val).toLocaleString('zh-CN');
}

// 通用分页 HTML 生成器
function buildPaginationHtml(currentPage, totalPages, pageSize, loadFnName) {
    if (totalPages < 1) {
        return '<li class="page-item disabled"><span class="page-link" style="color:#94a3b8;">暂无数据</span></li>';
    }
    const html = [];
    // 上一页
    html.push(`<li class="page-item ${currentPage <= 1 ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="${loadFnName}(${currentPage - 1});return false;">«</a></li>`);

    const maxShow = 7;
    let start = Math.max(1, currentPage - Math.floor(maxShow / 2));
    let end = Math.min(totalPages, start + maxShow - 1);
    if (end - start < maxShow - 1) start = Math.max(1, end - maxShow + 1);

    if (start > 1) {
        html.push(`<li class="page-item"><a class="page-link" href="#" onclick="${loadFnName}(1);return false;">1</a></li>`);
        if (start > 2) html.push(`<li class="page-item disabled"><span class="page-link">…</span></li>`);
    }
    for (let p = start; p <= end; p++) {
        html.push(`<li class="page-item ${p === currentPage ? 'active' : ''}">
            <a class="page-link" href="#" onclick="${loadFnName}(${p});return false;">${p}</a></li>`);
    }
    if (end < totalPages) {
        if (end < totalPages - 1) html.push(`<li class="page-item disabled"><span class="page-link">…</span></li>`);
        html.push(`<li class="page-item"><a class="page-link" href="#" onclick="${loadFnName}(${totalPages});return false;">${totalPages}</a></li>`);
    }
    // 下一页
    html.push(`<li class="page-item ${currentPage >= totalPages ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="${loadFnName}(${currentPage + 1});return false;">»</a></li>`);
    return html.join('');
}

// Toast 通知
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container') || _createToastContainer();
    const bgMap = { info: '#6366f1', success: '#10b981', warning: '#f59e0b', error: '#ef4444' };
    const iconMap = { info: 'ℹ️', success: '✅', warning: '⚠️', error: '❌' };
    const toast = document.createElement('div');
    toast.className = 'toast-item';
    toast.style.cssText = `background:${bgMap[type]};color:#fff;padding:10px 18px;border-radius:8px;
        margin-bottom:8px;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,.15);
        animation:slideInRight .3s ease;display:flex;align-items:center;gap:8px;`;
    toast.innerHTML = `<span>${iconMap[type]}</span> ${message}`;
    container.appendChild(toast);
    setTimeout(() => { toast.style.animation = 'slideOutRight .3s ease forwards';
        setTimeout(() => toast.remove(), 300); }, 3000);
}

function _createToastContainer() {
    const div = document.createElement('div');
    div.id = 'toast-container';
    div.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;';
    document.body.appendChild(div);
    return div;
}

// 添加 CSS 动画 (只加一次)
if (!document.getElementById('toast-animations')) {
    const style = document.createElement('style');
    style.id = 'toast-animations';
    style.textContent = `
        @keyframes slideInRight { from { transform: translateX(120%); opacity:0; } to { transform: translateX(0); opacity:1; } }
        @keyframes slideOutRight { from { transform: translateX(0); opacity:1; } to { transform: translateX(120%); opacity:0; } }
    `;
    document.head.appendChild(style);
}
