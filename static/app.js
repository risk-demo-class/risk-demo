/**
 * 物流风控系统 - 公共前端工具函数
 */

// 风险等级对应的Badge类名
function getRiskBadgeClass(level) {
    const map = {
        '低': 'badge-risk-low',
        '中': 'badge-risk-mid',
        '高': 'badge-risk-high',
        '极高': 'badge-risk-critical',
    };
    return map[level] || 'bg-secondary';
}

/**
 * 前端兜底的英文错误 -> 中文替换 (防止后端翻译没覆盖到的漏网英文跑到用户面前).
 * 按最长优先替换 (避免 "valid integer" 先被替换, 导致更长的 "Input should be a valid integer" 匹配不上).
 */
function _zhMsgFallback(msg) {
    if (typeof msg !== 'string') return msg;
    const map = [
        ['Input should be a valid integer',     '必须是合法整数'],
        ['Input should be a valid number',      '必须是合法数字'],
        ['Input should be a valid string',      '必须是合法字符串'],
        ['Input should be a valid boolean',     '必须是 true 或 false'],
        ['Input should be a valid list',        '必须是数组 (list)'],
        ['Input should be a valid dictionary',  '必须是对象 (dict)'],
        ['Input should be a valid datetime',    '必须是合法日期时间 (ISO 格式)'],
        ['Input should be a valid date',        '必须是合法日期 (YYYY-MM-DD)'],
        ['Input should be a valid object',      '必须是合法对象'],
        ['String should have at least',         '字符串长度至少 '],
        ['String should have at most',          '字符串长度最多 '],
        ['characters',                          ' 个字符'],
        ['Input should be greater than or equal to', '值必须大于等于'],
        ['Input should be less than or equal to',    '值必须小于等于'],
        ['Input should be greater than',        '值必须大于'],
        ['Input should be less than',           '值必须小于'],
        ['Value error,',                        '值错误:'],
        ['Field required',                      '缺少必填字段'],
        ['Invalid JSON',                        'JSON 格式非法'],
    ];
    let out = msg;
    for (const [en, zh] of map) {
        out = out.split(en).join(zh);
    }
    // 兜底 literal_error 里 "Expected one of: ['a','b']" → 中文表达
    out = out.replace(/Expected one of:\s*\[([^\]]+)\]/g, '允许值: $1');
    return out;
}

/**
 * 把 FastAPI/Pydantic 返回的 detail 错误对象统一转成可读字符串.
 * - string → 原样返回 (经过 _zhMsgFallback 兜底中文)
 * - {msg, loc} (单条错误) → "[loc] msg"
 * - [{msg, loc}...] (多条 422) → 每条一行用 <br> 分隔
 * - object (其他 dict) → JSON.stringify 2 空格缩进
 * - array 非对象项 → toString
 */
function formatHttpDetail(detail) {
    if (detail == null) return '请求失败';
    if (typeof detail === 'string') return _zhMsgFallback(detail);
    if (Array.isArray(detail)) {
        if (detail.length === 0) return '请求失败';
        if (detail.length === 1) return formatHttpDetail(detail[0]);
        return detail.map(formatHttpDetail).join('<br>');
    }
    if (typeof detail === 'object') {
        if (typeof detail.msg === 'string') {
            const loc = Array.isArray(detail.loc) && detail.loc.length > 0
                ? `[${detail.loc.join('.')}] `
                : '';
            return `${loc}${_zhMsgFallback(detail.msg)}`;
        }
        try {
            return JSON.stringify(detail, null, 2);
        } catch (_) {
            return String(detail);
        }
    }
    return String(detail);
}

// 通用API请求封装
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: { 'Content-Type': 'application/json' },
    };
    const res = await fetch(url, { ...defaultOptions, ...options });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '请求失败' }));
        throw new Error(formatHttpDetail(err.detail) || `HTTP ${res.status}`);
    }
    return res.json();
}

/**
 * ML P(拒绝) → 0-100 风险分 (sigmoid 风格校准, 跟 Python 端 _ml_prob_to_risk_score 一致).
 *
 * 【P4-L4 2026-08-08】前端显示统一: 0-100 风险分而不是 0-1 概率, 跟规则分语义一致.
 * 公式: risk_score = 100 * (1 - exp(-k * prob)), k=3
 * 校准点: 0.0→0, 0.1→26, 0.3→59, 0.5→78, 0.7→90, 0.9→97, 1.0→100
 */
function mlProbToRiskScore(prob, k = 3) {
    if (prob == null || isNaN(prob)) return null;
    if (prob <= 0) return 0;
    if (prob >= 1) return 100;
    return Math.round(100 * (1 - Math.exp(-k * prob)));
}

/**
 * 渲染 ML 评分 HTML 片段 (P(拒绝) + 风险分(sigmoid 校准) + ML 决策).
 * 用于风险检查/案件详情/评估历史 三个页面的统一展示.
 */
function renderMLScoreBlock(mlScore, mlDecision) {
    if (mlScore == null) {
        return '<span class="text-muted">未加载模型</span>';
    }
    const riskScore = mlProbToRiskScore(mlScore);
    const pct = (mlScore * 100).toFixed(2);
    const raw = mlScore.toFixed(4);
    const decision = mlDecision
        ? `<span class="badge bg-info">${mlDecision}</span>`
        : '<span class="text-muted">-</span>';
    return `
        P(拒绝): <strong>${pct}%</strong> <small class="text-muted">(${raw})</small><br>
        风险分 (sigmoid 校准): <strong>${riskScore}</strong> <small class="text-muted">/ 100</small><br>
        ML 决策: ${decision}
    `;
}

/**
 * 通用分页 HTML 生成器 (P4-L4 2026-08-08)
 *
 * 设计:
 *   - 最多同时显示 10 个页码 (含 首页/末页 + 上下页 + 省略号)
 *   - 中间用 `...` 占位, 点击跳 ±5 页 (避免点击无意义)
 *   - 末页用 `>>` 单独跳到最后一页 (兼容用户提到的 `>>>` 风格)
 *   - 兼容 totalPages <= 7: 直接显示所有页码, 不省略
 *
 * 参数:
 *   currentPage: 当前页 (1-based)
 *   totalPages: 总页数
 *   pageSize: 每页条数 (用于显示 "X 条/页" 信息)
 *   loadFnName: 加载函数名字符串 (例如 'loadAssessments' / 'loadCases')
 *   containerId: 分页 ul 元素的 id (默认 'pagination')
 *
 * 返回: HTML 字符串, 直接 innerHTML 到 ul 容器即可
 */
function buildPaginationHtml(currentPage, totalPages, pageSize, loadFnName, containerId = 'pagination') {
    if (totalPages < 1) {
        // 【P4-L4 2026-08-08v2】无数据也渲染"暂无数据"占位条, 避免底栏空白让用户以为出 bug
        return '<li class="page-item disabled"><span class="page-link text-muted" style="cursor:default;">暂无数据</span></li>';
    }
    // totalPages >= 1 都渲染 (包括 =1, 占位"上一页 1 下一页"让用户看到分页栏在工作, 不显空白)

    const html = [];
    const addItem = (label, page, opts = {}) => {
        const { active = false, disabled = false, isEllipsis = false } = opts;
        if (disabled) {
            html.push(`<li class="page-item disabled"><span class="page-link">${label}</span></li>`);
        } else if (isEllipsis) {
            // 省略号: 点击跳 ±5 页 (避免点无意义)
            const jumpTo = page;
            html.push(
                `<li class="page-item"><a class="page-link" href="#" `
                + `onclick="${loadFnName}(${jumpTo});return false;" `
                + `title="跳到第 ${jumpTo} 页" style="cursor:pointer;">...</a></li>`
            );
        } else {
            html.push(
                `<li class="page-item ${active ? 'active' : ''}">`
                + `<a class="page-link" href="#" onclick="${loadFnName}(${page});return false;">${label}</a></li>`
            );
        }
    };

    // 上一页 (单字符紧凑版, P4-L4 2026-08-08 第二轮)
    addItem('«', currentPage - 1, { disabled: currentPage <= 1 });

    // 总页数 <= 7, 直接全显示
    if (totalPages <= 7) {
        for (let i = 1; i <= totalPages; i++) {
            addItem(String(i), i, { active: i === currentPage });
        }
    } else {
        // 总页数 > 7, 用 ... 省略号
        // 总是显示首页
        addItem('1', 1, { active: currentPage === 1 });

        // 左边省略号: 当前页 > 4 时显示 (跳到 currentPage-3)
        if (currentPage > 4) {
            addItem('...', Math.max(2, currentPage - 3), { isEllipsis: true });
        }

        // 中间页码: max(2, currentPage-2) ... min(totalPages-1, currentPage+2)
        const start = Math.max(2, currentPage - 2);
        const end = Math.min(totalPages - 1, currentPage + 2);
        for (let i = start; i <= end; i++) {
            addItem(String(i), i, { active: i === currentPage });
        }

        // 右边省略号: 当前页 < totalPages-3 时显示 (跳到 currentPage+3)
        if (currentPage < totalPages - 3) {
            addItem('...', Math.min(totalPages - 1, currentPage + 3), { isEllipsis: true });
        }

        // 末页 (总是显示)
        addItem(String(totalPages), totalPages, { active: currentPage === totalPages });
    }

    // 下一页 (单字符紧凑版)
    addItem('»', currentPage + 1, { disabled: currentPage >= totalPages });

    // 末页快捷跳: 只有在 totalPages > 10 才显示 (单字符, 不再双 »»)
    if (totalPages > 10 && currentPage < totalPages) {
        html.push(
            `<li class="page-item">`
            + `<a class="page-link" href="#" onclick="${loadFnName}(${totalPages});return false;" `
            + `title="跳到末页 (第 ${totalPages} 页)" style="cursor:pointer;">››</a></li>`
        );
    }

    return html.join('');
}

/**
 * 全局 Toast 提示 (替代原生 alert, 避免 [object Object] 弹窗打断).
 * - success: 绿色 (bg-success)
 * - error:   红色 (bg-danger, role=alert)
 * - warning: 黄色 (bg-warning)
 * - info:    蓝色 (bg-info, 默认)
 * message 支持 <br> 换行 (formatHttpDetail 输出就是 <br> 分隔).
 */
function showToast(type, message, duration = 3000) {
    const wrap = document.getElementById('globalToastWrap');
    if (!wrap) {
        console.warn('[showToast] 全局 Toast 容器未就绪, 回退 console:', message);
        return;
    }
    const bgCls = type === 'success' ? 'text-bg-success'
        : type === 'error'   ? 'text-bg-danger'
        : type === 'warning' ? 'text-bg-warning text-dark'
        :                      'text-bg-info';
    const role   = type === 'error' ? 'alert' : 'status';
    const ariaLv = type === 'error' ? 'assertive' : 'polite';
    const id = 'toast-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
    const div = document.createElement('div');
    div.id = id;
    div.className = `toast ${bgCls} border-0 align-items-center mb-2`;
    div.setAttribute('role', role);
    div.setAttribute('aria-live', ariaLv);
    div.setAttribute('data-bs-delay', String(duration));
    div.setAttribute('data-bs-autohide', 'true');
    div.innerHTML = `
        <div class="d-flex w-100">
            <div class="toast-body flex-grow-1" style="white-space:pre-wrap;">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto"
                    data-bs-dismiss="toast" aria-label="关闭"></button>
        </div>`;
    wrap.appendChild(div);
    const toast = new bootstrap.Toast(div, { delay: duration, autohide: true });
    div.addEventListener('hidden.bs.toast', () => div.remove());
    toast.show();
}

/**
 * 打开全局「使用指引」模态框.
 * @param {string=} anchorId  可选: 打开后滚动到哪个章节 id
 *   可用值: guide-dashboard | guide-risk-check | guide-assessments |
 *           guide-rules     | guide-blacklist     | guide-cases      | guide-chat
 * @param {string=} tabTarget 可选: 先切换到哪个 Tab (默认 guideTabPages)
 */
function openGuideModal(anchorId, tabTarget) {
    const modalEl = document.getElementById('guideModal');
    if (!modalEl) {
        console.warn('[openGuideModal] #guideModal 没找到 (base.html 没注入?)');
        return;
    }
    // 1) 先切 Tab (再 show, 否则元素 hidden.scrollIntoView 无效)
    const tab = tabTarget || 'guideTabPages';
    const tabBtn = document.querySelector(`.nav-tabs button[data-bs-target="#${tab}"]`);
    if (tabBtn) bootstrap.Tab.getOrCreateInstance(tabBtn).show();

    // 2) 打开模态框
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl, { backdrop: true });
    modal.show();

    // 3) 滚动到锚点 (等 modal shown.bs.modal 后再滚, 避免高度为 0)
    if (anchorId) {
        const go = () => {
            const el = document.getElementById(anchorId);
            if (el) {
                // 滚到 Tab 内容容器顶部, 避免 sticky header 遮挡
                el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            modalEl.removeEventListener('shown.bs.modal', go);
        };
        modalEl.addEventListener('shown.bs.modal', go);
    }
}

