/* 制造业风控系统 - 全站公共前端工具 (badge 映射 + fetch 封装) */

// 风险等级 → Bootstrap 徽章 CSS 类 (低/中/高/极高)
function getRiskBadgeClass(level) {
    switch (level) {
        case '低': return 'badge-risk-low';
        case '中': return 'badge-risk-mid';
        case '高': return 'badge-risk-high';
        case '极高': return 'badge-risk-critical';
        default: return 'bg-secondary';
    }
}

// 决策 → 徽章颜色
function getDecisionBadgeClass(decision) {
    switch (decision) {
        case '通过': return 'bg-success';
        case '标记': return 'bg-warning text-dark';
        case '人工审核': return 'bg-primary';
        case '拒绝': return 'bg-danger';
        default: return 'bg-secondary';
    }
}

// 统一 fetch 封装: 加 JSON 头 + 统一错误处理
async function apiRequest(url, options = {}) {
    const opts = {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    };
    if (opts.body && typeof opts.body !== 'string') {
        opts.body = JSON.stringify(opts.body);
    }
    const resp = await fetch(url, opts);
    let data = null;
    try {
        data = await resp.json();
    } catch (e) {
        data = { detail: '响应解析失败' };
    }
    if (!resp.ok) {
        const msg = data && data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : `HTTP ${resp.status}`;
        throw new Error(msg);
    }
    return data;
}

// 渲染风险徽章 HTML
function riskBadge(level) {
    return `<span class="badge ${getRiskBadgeClass(level)}">${level}</span>`;
}

// 渲染决策徽章 HTML
function decisionBadge(decision) {
    return `<span class="badge ${getDecisionBadgeClass(decision)}">${decision}</span>`;
}

// 格式化时间 (YYYY-MM-DD HH:mm)
function formatTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
