/**
 * 电信风控系统 - 公共前端工具函数
 */

// 风险等级 Badge 类名
function getRiskBadgeClass(level) {
    const map = {
        '低': 'badge-risk-low',
        '中': 'badge-risk-mid',
        '高': 'badge-risk-high',
        '极高': 'badge-risk-critical',
    };
    return map[level] || 'bg-secondary';
}

// 决策 → Bootstrap badge
function getDecisionBadgeClass(d) {
    const map = {
        '通过': 'bg-success',
        '标记': 'bg-info',
        '人工审核': 'bg-warning text-dark',
        '拒绝': 'bg-danger',
        '关停号码': 'bg-dark',
        '推送公安': 'bg-danger',
    };
    return map[d] || 'bg-secondary';
}

// 通用 API 请求封装
async function apiRequest(url, options = {}) {
    const defaultOptions = { headers: { 'Content-Type': 'application/json' } };
    const res = await fetch(url, { ...defaultOptions, ...options });
    if (!res.ok) {
        const text = await res.text().catch(() => '');
        let detail = `HTTP ${res.status}`;
        try {
            const err = JSON.parse(text);
            if (err.detail !== undefined) {
                detail = typeof err.detail === 'string'
                    ? err.detail
                    : (err.detail && typeof err.detail === 'object'
                        ? (err.detail.msg || err.detail.message || err.detail.error || JSON.stringify(err.detail))
                        : `HTTP ${res.status}`);
            } else if (err.message) {
                detail = err.message;
            }
        } catch (e) {
            // 非 JSON 错误响应 (如 uvicorn 的 Internal Server Error 纯文本)
            if (text && text.length < 200) detail = `${text.trim()} (${res.status})`;
        }
        throw new Error(detail);
    }
    return res.json();
}

// ML P(高风险) → 0-100 风险分 (sigmoid 校准, 与后端 _ml_prob_to_risk_score 对齐)
function mlProbToRiskScore(prob, k = 3) {
    if (prob == null || isNaN(prob)) return null;
    if (prob <= 0) return 0;
    if (prob >= 1) return 100;
    return Math.round(100 * (1 - Math.exp(-k * prob)));
}

// 渲染 ML 评分块
function renderMLScoreBlock(mlScore, mlDecision) {
    if (mlScore == null) {
        return '<span class="text-muted">未加载模型</span>';
    }
    const riskScore = mlProbToRiskScore(mlScore);
    const pct = (mlScore * 100).toFixed(2);
    const raw = Number(mlScore).toFixed(4);
    const decision = mlDecision
        ? `<span class="badge bg-info">${mlDecision}</span>`
        : '<span class="text-muted">-</span>';
    return `
        P(高风险): <strong>${pct}%</strong> <small class="text-muted">(${raw})</small><br>
        风险分 (sigmoid): <strong>${riskScore}</strong> <small class="text-muted">/ 100</small><br>
        ML 决策: ${decision}
    `;
}

// 规则命中条目 → 列表行 HTML
function renderRuleItem(rule) {
    const badge = `<span class="badge ${getRiskBadgeClass(rule.risk_level)}">${rule.risk_level}</span>`;
    return `<span class="me-2">${badge}</span>${rule.rule_name} <small class="text-muted">(${rule.rule_id || ''} · ${rule.risk_score}分 · ${rule.action})</small>`;
}

// 通用分页 HTML 生成器
function buildPaginationHtml(currentPage, totalPages, pageSize, loadFnName) {
    if (totalPages < 1) {
        return '<li class="page-item disabled"><span class="page-link text-muted" style="cursor:default;">暂无数据</span></li>';
    }
    const html = [];
    const addItem = (label, page, opts = {}) => {
        const { active = false, disabled = false, isEllipsis = false } = opts;
        if (disabled) {
            html.push(`<li class="page-item disabled"><span class="page-link">${label}</span></li>`);
        } else if (isEllipsis) {
            html.push(`<li class="page-item"><a class="page-link" href="#" onclick="${loadFnName}(${page});return false;" title="跳到第 ${page} 页" style="cursor:pointer;">...</a></li>`);
        } else {
            html.push(`<li class="page-item ${active ? 'active' : ''}"><a class="page-link" href="#" onclick="${loadFnName}(${page});return false;">${label}</a></li>`);
        }
    };
    addItem('«', currentPage - 1, { disabled: currentPage <= 1 });
    if (totalPages <= 7) {
        for (let i = 1; i <= totalPages; i++) addItem(String(i), i, { active: i === currentPage });
    } else {
        addItem('1', 1, { active: currentPage === 1 });
        if (currentPage > 4) addItem('...', Math.max(2, currentPage - 3), { isEllipsis: true });
        const start = Math.max(2, currentPage - 2);
        const end = Math.min(totalPages - 1, currentPage + 2);
        for (let i = start; i <= end; i++) addItem(String(i), i, { active: i === currentPage });
        if (currentPage < totalPages - 3) addItem('...', Math.min(totalPages - 1, currentPage + 3), { isEllipsis: true });
        addItem(String(totalPages), totalPages, { active: currentPage === totalPages });
    }
    addItem('»', currentPage + 1, { disabled: currentPage >= totalPages });
    return html.join('');
}

// 粘底分页栏渲染 (对应 base.html .pagination-bottom)
function renderPaginationBar(containerId, currentPage, totalPages, total, pageSize, loadFnName) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const info = `<span class="text-muted small me-3">共 ${total} 条 · ${pageSize} 条/页</span>`;
    const ul = `<ul class="pagination mb-0">${buildPaginationHtml(currentPage, totalPages, pageSize, loadFnName)}</ul>`;
    el.innerHTML = info + ul;
}
