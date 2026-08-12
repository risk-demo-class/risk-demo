/* ==========================================================================
   core.js —— 基础设施：DOM / API / 通知 / 弹窗 / 风控域格式化
   零依赖，无构建步骤，无 CDN。挂在 window.X 下。
   ========================================================================== */
(function (global) {
  "use strict";

  /* ================================================================ DOM */
  /** 极简 createElement：h("div.card", {onclick}, [children]) */
  function h(spec, props, children) {
    var parts = String(spec).split(/(?=[.#])/);
    var el = document.createElement(parts[0] || "div");
    for (var i = 1; i < parts.length; i++) {
      var p = parts[i];
      if (p[0] === ".") { var c = p.slice(1).trim().replace(/\s+/g, " "); if (c && c.indexOf(" ") === -1) el.classList.add(c); }
      else if (p[0] === "#") el.id = p.slice(1).trim();
    }
    if (props) {
      for (var k in props) {
        if (!Object.prototype.hasOwnProperty.call(props, k)) continue;
        var v = props[k];
        if (v === null || v === undefined || v === false) continue;
        if (k === "html") el.innerHTML = v;
        else if (k === "text") el.textContent = v;
        else if (k === "class") { var cc = String(v).trim().replace(/\s+/g, " "); if (cc) el.className += (el.className ? " " : "") + cc; }
        else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
        else if (k.slice(0, 2) === "on" && typeof v === "function") {
          el.addEventListener(k.slice(2).toLowerCase(), v);
        } else if (k === "dataset" && typeof v === "object") Object.assign(el.dataset, v);
        else el.setAttribute(k, v);
      }
    }
    appendChildren(el, children);
    return el;
  }

  function appendChildren(el, children) {
    if (children === null || children === undefined || children === false) return;
    if (Array.isArray(children)) {
      children.forEach(function (c) { appendChildren(el, c); });
      return;
    }
    if (children instanceof Node) { el.appendChild(children); return; }
    el.appendChild(document.createTextNode(String(children)));
  }

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  };
  function clear(el) { while (el && el.firstChild) el.removeChild(el.firstChild); return el; }
  function mount(el, children) { clear(el); appendChildren(el, children); return el; }

  /** HTML 转义 —— 任何拼进 innerHTML 的后端数据都必须过这一层 */
  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------------------------------------------------------------- 图标 */
  var ICON_PATHS = {
    gauge: "M12 14l4-4M4.9 19.1A10 10 0 1119.1 19.1M12 14a1.5 1.5 0 100-3 1.5 1.5 0 000 3z",
    shield: "M12 3l7 2.7v5.6c0 4.4-3 7.9-7 9.2-4-1.3-7-4.8-7-9.2V5.7L12 3zM9 12l2.1 2.1L15.5 9.6",
    history: "M12 8v4l3 2M3.1 12a9 9 0 1018 0 9 9 0 00-18 0M3 12H1m2 0l2-2",
    folder: "M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z",
    rules: "M9 5h10M9 12h10M9 19h10M4.5 5h.01M4.5 12h.01M4.5 19h.01",
    ban: "M12 3a9 9 0 100 18 9 9 0 000-18zM5.6 5.6l12.8 12.8",
    user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c0-3.6 3.6-6 8-6s8 2.4 8 6",
    table: "M3 5h18v14H3V5zm0 5h18M9 10v9m6-9v9",
    robot: "M8 11h.01M16 11h.01M9 16h6M6 7h12a2 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2V9a2 2 0 012-2zM12 4v3",
    brain: "M9 4a3 3 0 00-3 3 3 3 0 00-1 5.8V16a3 3 0 003 3h1V4H9zM15 4a3 3 0 013 3 3 3 0 011 5.8V16a3 3 0 01-3 3h-1V4h0z",
    cog: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 01-2.8 2.8l-.1-.1a1.7 1.7 0 00-2.9 1.2V21a2 2 0 01-4 0v-.1A1.7 1.7 0 006 19.7l-.1.1a2 2 0 11-2.8-2.8l.1-.1A1.7 1.7 0 003 15H3a2 2 0 010-4h.1A1.7 1.7 0 004.3 8L4.2 8a2 2 0 012.8-2.8l.1.1A1.7 1.7 0 0010 4.3V3a2 2 0 014 0v.1a1.7 1.7 0 002.9 1.2l.1-.1a2 2 0 012.8 2.8l-.1.1A1.7 1.7 0 0021 11h0a2 2 0 010 4h-.1a1.7 1.7 0 00-1.5 1z",
    log: "M8 4h9a2 2 0 012 2v12a2 2 0 01-2 2H8M8 4a2 2 0 00-2 2v12a2 2 0 002 2M11 9h5M11 13h5",
    check: "M4 12.5l5 5L20 6.5",
    x: "M6 6l12 12M18 6L6 18",
    warn: "M12 9v4m0 3h.01M10.3 3.9L2.4 17.5A2 2 0 004.1 20.5h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",
    info: "M12 16v-4m0-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
    arrowR: "M5 12h14M13 6l6 6-6 6",
    chevR: "M9 6l6 6-6 6",
    plus: "M12 5v14M5 12h14",
    search: "M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4",
    trash: "M4 7h16M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2M6 7l1 13a1 1 0 001 1h8a1 1 0 001-1l1-13",
    edit: "M4 20h4L19 9a2.1 2.1 0 00-3-3L5 17v3zM14 6l4 4",
    play: "M7 4l13 8-13 8V4z",
    inbox: "M4 13h4l2 3h4l2-3h4M4 13l2.5-8h11L20 13v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5z",
    reload: "M20 11a8 8 0 10-2.3 5.7M20 5v6h-6",
    send: "M4 12l16-8-6 16-3-6-7-2z",
    bolt: "M13 3L5 14h6l-1 7 8-11h-6l1-7z"
  };

  function icon(name, size, cls) {
    var d = ICON_PATHS[name] || ICON_PATHS.info;
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", size || 16);
    svg.setAttribute("height", size || 16);
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.9");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    if (cls) svg.setAttribute("class", cls);
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.appendChild(path);
    return svg;
  }

  /* ================================================================ API */
  var API_BASE = "";

  function buildQuery(params) {
    if (!params) return "";
    var pairs = [];
    Object.keys(params).forEach(function (k) {
      var v = params[k];
      if (v === null || v === undefined || v === "") return;
      pairs.push(encodeURIComponent(k) + "=" + encodeURIComponent(v));
    });
    return pairs.length ? "?" + pairs.join("&") : "";
  }

  /**
   * 统一请求入口。
   * 后端错误统一是 {detail: "..."}（framework.HTTPError），这里翻译成 Error 抛出，
   * 页面只管 try/catch + toast，不用各自解析。
   */
  function request(method, path, options) {
    options = options || {};
    var url = API_BASE + path + buildQuery(options.params);
    var init = { method: method, headers: {} };
    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    return fetch(url, init).then(function (res) {
      var ct = res.headers.get("Content-Type") || "";
      var parse = ct.indexOf("application/json") >= 0
        ? res.json().catch(function () { return {}; })
        : res.text();
      return parse.then(function (data) {
        if (res.ok) return data;
        var msg = (data && (data.detail || data.message)) || res.statusText ||
                  ("HTTP " + res.status);
        var err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        err.status = res.status;
        err.payload = data;
        throw err;
      });
    });
  }

  var api = {
    get: function (p, params) { return request("GET", p, { params: params }); },
    post: function (p, body, params) { return request("POST", p, { body: body, params: params }); },
    put: function (p, body) { return request("PUT", p, { body: body }); },
    del: function (p) { return request("DELETE", p); },

    /** SSE 流式读取（宝典 11.4）。返回 abort 函数。 */
    stream: function (path, body, handlers) {
      handlers = handlers || {};
      var ctrl = new AbortController();
      fetch(API_BASE + path, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(body),
        signal: ctrl.signal
      }).then(function (res) {
        if (!res.ok) {
          return res.text().then(function (t) {
            var d;
            try { d = JSON.parse(t); } catch (e) { d = {}; }
            throw new Error(d.detail || t || ("HTTP " + res.status));
          });
        }
        var reader = res.body.getReader();
        var decoder = new TextDecoder("utf-8");
        var buf = "";
        function pump() {
          return reader.read().then(function (r) {
            if (r.done) {
              if (handlers.done) handlers.done();
              return;
            }
            buf += decoder.decode(r.value, { stream: true });
            // SSE 以空行分隔事件
            var blocks = buf.split(/\n\n/);
            buf = blocks.pop();
            blocks.forEach(function (block) {
              var lines = block.split(/\n/);
              var dataLines = [];
              var evt = "message";
              lines.forEach(function (line) {
                if (line.indexOf("data:") === 0) dataLines.push(line.slice(5).replace(/^ /, ""));
                else if (line.indexOf("event:") === 0) evt = line.slice(6).trim();
              });
              if (!dataLines.length) return;
              var raw = dataLines.join("\n");
              if (raw === "[DONE]") { if (handlers.done) handlers.done(); return; }
              var payload;
              try { payload = JSON.parse(raw); } catch (e) { payload = { text: raw }; }
              if (handlers.event) handlers.event(evt, payload);
            });
            return pump();
          });
        }
        return pump();
      }).catch(function (err) {
        if (err.name === "AbortError") return;
        if (handlers.error) handlers.error(err);
      });
      return function () { ctrl.abort(); };
    }
  };

  /* ================================================================ Toast */
  function toast(message, type, title) {
    var wrap = $("#toast-wrap");
    if (!wrap) return;
    var el = h("div.toast" + (type ? ".t-" + type : ""), null, [
      icon(type === "danger" ? "warn" : type === "warn" ? "warn" : type === "ok" ? "check" : "info",
           16, null),
      h("div", { style: { flex: "1", minWidth: "0" } }, [
        title ? h("b", { text: title }) : null,
        h("p", { text: message })
      ]),
      h("button.icon-btn", {
        onclick: function () { dismiss(); },
        "aria-label": "关闭"
      }, icon("x", 13))
    ]);
    wrap.appendChild(el);
    var timer = setTimeout(dismiss, type === "danger" ? 6500 : 3600);
    function dismiss() {
      clearTimeout(timer);
      if (!el.parentNode) return;
      el.classList.add("out");
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 200);
    }
    return dismiss;
  }
  toast.ok = function (m, t) { return toast(m, "ok", t); };
  toast.warn = function (m, t) { return toast(m, "warn", t); };
  toast.err = function (m, t) { return toast(m, "danger", t || "操作失败"); };

  /* ================================================================ Modal */
  var modalState = { onClose: null };

  function modal(opts) {
    opts = opts || {};
    var mask = $("#modal-mask");
    var box = $(".modal", mask);
    var title = $("#modal-title");
    var body = $("#modal-body");
    var foot = $("#modal-foot");

    box.className = "modal" + (opts.width ? " w-" + opts.width : "");
    title.textContent = opts.title || "";
    mount(body, opts.content);
    clear(foot);
    (opts.actions || []).forEach(function (a) {
      foot.appendChild(h("button.btn" + (a.variant ? ".btn-" + a.variant : ""), {
        text: a.label,
        onclick: function () {
          if (a.onClick) {
            var r = a.onClick();
            if (r === false) return;
          }
          if (a.keepOpen !== true) closeModal();
        }
      }));
    });
    modalState.onClose = opts.onClose || null;
    mask.hidden = false;
    return { close: closeModal, body: body, foot: foot };
  }

  function closeModal() {
    var mask = $("#modal-mask");
    if (!mask || mask.hidden) return;
    mask.hidden = true;
    if (modalState.onClose) { try { modalState.onClose(); } catch (e) { /* noop */ } }
    modalState.onClose = null;
  }

  function confirmModal(opts) {
    return new Promise(function (resolve) {
      modal({
        title: opts.title || "确认操作",
        width: "sm",
        content: [
          h("p", { text: opts.message || "" }),
          opts.detail ? h("p.mut.f-12.mt10", { text: opts.detail }) : null
        ],
        actions: [
          { label: opts.cancelText || "取消", onClick: function () { resolve(false); } },
          {
            label: opts.okText || "确定",
            variant: opts.danger ? "danger" : "primary",
            onClick: function () { resolve(true); }
          }
        ],
        onClose: function () { resolve(false); }
      });
    });
  }

  /* ================================================================ 格式化 */
  function num(v, digits) {
    if (v === null || v === undefined || v === "") return "-";
    var n = Number(v);
    if (isNaN(n)) return String(v);
    if (digits === undefined) {
      return n.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
    }
    return n.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  /** 金额：默认 ¥ + 千分位（中国区约定） */
  function money(v, digits) {
    if (v === null || v === undefined || v === "") return "-";
    var n = Number(v);
    if (isNaN(n)) return String(v);
    return "¥" + n.toLocaleString("zh-CN", {
      minimumFractionDigits: digits === undefined ? 2 : digits,
      maximumFractionDigits: digits === undefined ? 2 : digits
    });
  }

  function pct(v, digits) {
    if (v === null || v === undefined || v === "") return "-";
    var n = Number(v);
    if (isNaN(n)) return String(v);
    if (n <= 1 && n >= -1) n = n * 100;
    return n.toFixed(digits === undefined ? 1 : digits) + "%";
  }

  /** 后端时间统一 "YYYY-MM-DD HH:MM:SS"，这里只做裁剪，不做时区换算 */
  function dt(v, mode) {
    if (!v) return "-";
    var s = String(v).replace("T", " ").slice(0, 19);
    if (mode === "date") return s.slice(0, 10);
    if (mode === "short") return s.slice(5, 16);
    if (mode === "time") return s.slice(11, 19);
    return s;
  }

  function ago(v) {
    if (!v) return "-";
    var t = new Date(String(v).replace(/-/g, "/").replace("T", " ")).getTime();
    if (isNaN(t)) return dt(v, "short");
    var diff = Math.floor((Date.now() - t) / 1000);
    if (diff < 60) return diff <= 0 ? "刚刚" : diff + " 秒前";
    if (diff < 3600) return Math.floor(diff / 60) + " 分钟前";
    if (diff < 86400) return Math.floor(diff / 3600) + " 小时前";
    if (diff < 2592000) return Math.floor(diff / 86400) + " 天前";
    return dt(v, "date");
  }

  function trunc(s, n) {
    s = s === null || s === undefined ? "" : String(s);
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  /* ================================================================ 风控域映射 */
  /** 四决策 → 颜色（宝典 8.3） */
  var DECISION_TAG = { "通过": "green", "标记": "cyan", "人工审核": "orange", "拒绝": "red" };
  var DECISION_KEY = { "通过": "pass", "标记": "mark", "人工审核": "review", "拒绝": "reject" };
  /** 四风险等级 → 颜色 */
  var LEVEL_TAG = { "低": "green", "中": "cyan", "高": "orange", "极高": "red" };
  var LEVEL_KEY = { "低": "low", "中": "mid", "高": "high", "极高": "top" };
  /** 五案件状态 → 颜色（宝典 9.2） */
  var CASE_TAG = {
    "待审核": "orange", "审核中": "blue", "已通过": "green", "已拒绝": "red", "已关闭": "gray"
  };
  var CASE_ORDER = ["待审核", "审核中", "已通过", "已拒绝", "已关闭"];
  /** 特征维度 → 颜色 */
  var DIM_TAG = { "用户": "blue", "学习": "cyan", "账号": "purple" };

  function tag(text, kind, extraCls) {
    return h("span.tag.tag-" + (kind || "gray") + (extraCls ? "." + extraCls : ""),
             { text: text === null || text === undefined ? "-" : String(text) });
  }
  function decisionTag(d) { return tag(d, DECISION_TAG[d] || "gray", "tag-dot"); }
  function levelTag(l) { return tag(l, LEVEL_TAG[l] || "gray", "tag-dot"); }
  function caseTag(s) { return tag(s, CASE_TAG[s] || "gray", "tag-dot"); }

  /** 分数 → 语义色类名 */
  function scoreClass(score) {
    var n = Number(score) || 0;
    if (n >= 80) return "c-danger";
    if (n >= 60) return "c-warn";
    if (n >= 30) return "c-info";
    return "c-ok";
  }

  /* ================================================================ 通用视图块 */
  function emptyBlock(text, sub) {
    return h("div.empty", null, [
      icon("inbox", 30),
      h("b", { text: text || "暂无数据" }),
      sub ? h("span", { text: sub }) : null
    ]);
  }

  function loadingBlock(text) {
    return h("div.loading-block", null, [h("span.spinner"), text || "加载中…"]);
  }

  function errorBlock(err, onRetry) {
    return h("div.empty", null, [
      icon("warn", 30),
      h("b", { text: "加载失败" }),
      h("span", { text: (err && err.message) || String(err) }),
      onRetry ? h("div.mt14", null,
        h("button.btn.btn-sm", { text: "重试", onclick: onRetry })) : null
    ]);
  }

  /** 声明式表格。columns: [{key,label,align,width,render,cls}] */
  function table(columns, rows, opts) {
    opts = opts || {};
    if (!rows || !rows.length) {
      return opts.empty === false ? null : emptyBlock(opts.emptyText, opts.emptySub);
    }
    var thead = h("thead", null, h("tr", null, columns.map(function (c) {
      return h("th", {
        text: c.label,
        class: c.align === "right" ? "t-r" : c.align === "center" ? "t-c" : "",
        style: c.width ? { width: c.width } : null
      });
    })));
    var tbody = h("tbody", null, rows.map(function (row, idx) {
      var tr = h("tr" + (opts.onRowClick ? ".is-clickable" : ""), {
        onclick: opts.onRowClick ? function () { opts.onRowClick(row, idx); } : null
      }, columns.map(function (c) {
        var content = c.render ? c.render(row, idx) : row[c.key];
        var cls = [];
        if (c.align === "right") cls.push("num");
        if (c.align === "center") cls.push("t-c");
        if (c.nowrap) cls.push("nowrap");
        if (c.cls) cls.push(c.cls);
        var td = h("td", { class: cls.join(" ") });
        if (content instanceof Node) td.appendChild(content);
        else if (Array.isArray(content)) appendChildren(td, content);
        else td.textContent = content === null || content === undefined ? "-" : String(content);
        return td;
      }));
      return tr;
    }));
    var cls = ".tbl" + (opts.zebra ? ".tbl-zebra" : "") + (opts.compact ? ".tbl-compact" : "");
    return h("div.tbl-wrap", null, h("table" + cls, null, [thead, tbody]));
  }

  /** 分页条。onChange(newOffset) */
  function pager(total, limit, offset, onChange) {
    var page = Math.floor(offset / limit) + 1;
    var pages = Math.max(Math.ceil(total / limit), 1);
    return h("div.pager", null, [
      h("span", null, ["共 ", h("b", { text: num(total, 0) }), " 条 · 第 ",
                       h("b", { text: page }), " / ", h("b", { text: pages }), " 页"]),
      h("span.spacer"),
      h("button.btn.btn-sm", {
        text: "上一页", disabled: offset <= 0,
        onclick: function () { onChange(Math.max(offset - limit, 0)); }
      }),
      h("button.btn.btn-sm", {
        text: "下一页", disabled: offset + limit >= total,
        onclick: function () { onChange(offset + limit); }
      })
    ]);
  }

  /** 统计卡 */
  function stat(label, value, opts) {
    opts = opts || {};
    return h("div.stat" + (opts.tone ? ".t-" + opts.tone : ""), null, [
      h("div.stat-label", null, [opts.icon ? icon(opts.icon, 13) : null, label]),
      h("div.stat-value", null, [
        value === null || value === undefined ? "-" : String(value),
        opts.unit ? h("small", { text: opts.unit }) : null
      ]),
      opts.sub ? h("div.stat-sub", null, opts.sub) : null
    ]);
  }

  /** 卡片外壳 */
  function card(title, bodyContent, opts) {
    opts = opts || {};
    var head = null;
    if (title || opts.actions || opts.sub) {
      head = h("div.card-head", null, [
        title ? h("h3", { text: title }) : null,
        opts.sub ? h("span.sub", { text: opts.sub }) : null,
        h("span.spacer"),
        opts.actions || null
      ]);
    }
    return h("div.card" + (opts.cls ? "." + opts.cls : ""), null, [
      head,
      h("div.card-body" + (opts.tight ? ".tight" : ""), null, bodyContent),
      opts.foot ? h("div.card-foot", null, opts.foot) : null
    ]);
  }

  function kv(pairs, opts) {
    var dl = h("dl.kv" + (opts && opts.two ? ".kv-2" : ""));
    pairs.forEach(function (p) {
      if (!p) return;
      dl.appendChild(h("dt", { text: p[0] }));
      var dd = h("dd");
      if (p[1] instanceof Node) dd.appendChild(p[1]);
      else dd.textContent = p[1] === null || p[1] === undefined || p[1] === "" ? "-" : String(p[1]);
      dl.appendChild(dd);
    });
    return dl;
  }

  function bar(ratio, tone, height) {
    var w = Math.max(0, Math.min(1, Number(ratio) || 0)) * 100;
    return h("div.bar" + (height ? ".h" + height : ""), null,
             h("i" + (tone ? ".c-" + tone : ""), { style: { width: w.toFixed(2) + "%" } }));
  }

  function alert(kind, title, body) {
    return h("div.alert.alert-" + kind, null, [
      icon(kind === "ok" ? "check" : kind === "info" ? "info" : "warn", 16),
      h("div", { style: { flex: "1", minWidth: "0" } }, [
        title ? h("b", { text: title }) : null,
        body ? (body instanceof Node ? body : h("span", { text: body })) : null
      ])
    ]);
  }

  /** JSON 高亮（只给对象/数组用，够读就行） */
  function jsonBlock(obj, light) {
    var text;
    try { text = JSON.stringify(obj, null, 2); } catch (e) { text = String(obj); }
    if (text === undefined) text = "";
    var html = esc(text)
      .replace(/&quot;([^&]*?)&quot;(\s*:)/g, '<span class="k">&quot;$1&quot;</span>$2')
      .replace(/:\s*&quot;([^&]*?)&quot;/g, ': <span class="s">&quot;$1&quot;</span>')
      .replace(/:\s*(-?\d+\.?\d*)/g, ': <span class="n">$1</span>')
      .replace(/:\s*(true|false|null)/g, ': <span class="n">$1</span>');
    return h("pre.code" + (light ? ".code-light" : ""), { html: html });
  }

  /* ---------------------------------------------------------------- 表单 */
  function field(label, control, opts) {
    opts = opts || {};
    return h("div.field", null, [
      h("label.label", null, [
        label,
        opts.required ? h("span.req", { text: "*" }) : null,
        opts.hint ? h("span.hint", { text: opts.hint }) : null
      ]),
      control,
      opts.tip ? h("div.field-tip", { text: opts.tip }) : null
    ]);
  }

  function input(props) {
    return h("input.input", Object.assign({ type: "text" }, props || {}));
  }

  function select(options, props) {
    var el = h("select.select", props || {});
    (options || []).forEach(function (o) {
      var value = typeof o === "object" ? o.value : o;
      var label = typeof o === "object" ? o.label : o;
      el.appendChild(h("option", { value: value, text: label }));
    });
    if (props && props.value !== undefined) el.value = props.value;
    return el;
  }

  function textarea(props) {
    return h("textarea.textarea", props || {});
  }

  /** 筛选栏：defs=[{key,label,type,options,placeholder,width}]，返回 {el, values()} */
  function filterBar(defs, onSubmit, opts) {
    opts = opts || {};
    var controls = {};
    var row = h("div.filters");
    defs.forEach(function (d) {
      var ctrl;
      if (d.type === "select") {
        ctrl = select(d.options, { value: d.value || "" });
      } else {
        ctrl = input({ placeholder: d.placeholder || "", value: d.value || "" });
        ctrl.addEventListener("keydown", function (e) {
          if (e.key === "Enter") submit();
        });
      }
      if (d.width) ctrl.style.width = d.width;
      controls[d.key] = ctrl;
      row.appendChild(h("div.field", { style: d.width ? { flex: "0 0 auto" } : null },
        [h("label.label", { text: d.label }), ctrl]));
    });
    function values() {
      var out = {};
      Object.keys(controls).forEach(function (k) {
        var v = controls[k].value;
        if (v !== "" && v !== null && v !== undefined) out[k] = v;
      });
      return out;
    }
    function submit() { onSubmit(values()); }
    row.appendChild(h("div.field", { style: { flex: "0 0 auto" } }, [
      h("label.label", { html: "&nbsp;" }),
      h("div.row", null, [
        h("button.btn.btn-primary.btn-sm", { onclick: submit }, [icon("search", 13), "查询"]),
        h("button.btn.btn-sm", {
          text: "重置",
          onclick: function () {
            Object.keys(controls).forEach(function (k) { controls[k].value = ""; });
            submit();
          }
        }),
        opts.extra || null
      ])
    ]));
    return { el: row, values: values, controls: controls, submit: submit };
  }

  /* ================================================================ 杂项 */
  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments, self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, wait || 250);
    };
  }

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () { toast.ok("已复制到剪贴板"); },
        function () { toast.warn("复制失败，请手动选择"); }
      );
      return;
    }
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); toast.ok("已复制到剪贴板"); }
    catch (e) { toast.warn("复制失败，请手动选择"); }
    document.body.removeChild(ta);
  }

  function groupBy(list, keyFn) {
    var out = {};
    (list || []).forEach(function (item) {
      var k = keyFn(item);
      (out[k] = out[k] || []).push(item);
    });
    return out;
  }

  global.X = {
    h: h, $: $, $$: $$, clear: clear, mount: mount, esc: esc, icon: icon,
    api: api, request: request,
    toast: toast, modal: modal, closeModal: closeModal, confirm: confirmModal,
    num: num, money: money, pct: pct, dt: dt, ago: ago, trunc: trunc,
    tag: tag, decisionTag: decisionTag, levelTag: levelTag, caseTag: caseTag,
    scoreClass: scoreClass,
    DECISION_TAG: DECISION_TAG, DECISION_KEY: DECISION_KEY,
    LEVEL_TAG: LEVEL_TAG, LEVEL_KEY: LEVEL_KEY,
    CASE_TAG: CASE_TAG, CASE_ORDER: CASE_ORDER, DIM_TAG: DIM_TAG,
    emptyBlock: emptyBlock, loadingBlock: loadingBlock, errorBlock: errorBlock,
    table: table, pager: pager, stat: stat, card: card, kv: kv, bar: bar,
    alert: alert, jsonBlock: jsonBlock,
    field: field, input: input, select: select, textarea: textarea, filterBar: filterBar,
    debounce: debounce, copy: copy, groupBy: groupBy
  };
})(window);
