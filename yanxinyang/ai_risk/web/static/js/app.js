/* ==========================================================================
   app.js —— SPA 路由 + 侧边栏渲染 + 顶部健康/模型状态指示灯
   零依赖。挂在 window.Pages（由各 pages-*.js 注册），本文件负责调度。
   ========================================================================== */
(function (global) {
  "use strict";
  var X = global.X;

  var PAGES = (global.__APP__ && global.__APP__.pages) || [];
  var pageMap = {};
  PAGES.forEach(function (p) { pageMap[p.key] = p; });

  /* 每个页面的标题 / 副标题（顶栏展示） */
  var META = {
    dashboard:   { title: "风控大盘",   desc: "实时监控风控核心指标与告警" },
    check:       { title: "风险检查",   desc: "触发一次 7 步流水线风控评估" },
    assessment:  { title: "评估历史",   desc: "查询与回溯历史风控评估记录" },
    case:        { title: "案件中心",   desc: "人工审核工单与 5 态状态机流转" },
    rule:        { title: "规则引擎",   desc: "30 条规则 / 6 大类 / 14 个算子" },
    blacklist:   { title: "黑名单",     desc: "失信名单管理（命中即一票否决）" },
    profile:     { title: "用户画像",   desc: "用户风险档案与业务统计" },
    business:    { title: "业务数据",   desc: "24 张表数据字典与原始数据浏览" },
    assistant:   { title: "AI 助手",    desc: "8 个工具的智能风控助理（本地意图路由）" },
    model:       { title: "模型中心",   desc: "XGBoost 模型状态与特征重要性" },
    config:      { title: "系统配置",   desc: "决策阈值 / 融合参数 / 告警阈值" },
    audit:       { title: "审计日志",   desc: "关键操作留痕与变更追溯" }
  };

  var pageCleanup = null;   // 上一个页面返回的清理函数（如 SSE 中止）

  /* ---------------------------------------------------------------- 导航 */
  function renderNav() {
    var nav = X.$("#nav");
    if (!nav) return;
    var groups = {};
    PAGES.forEach(function (p) {
      (groups[p.group] = groups[p.group] || []).push(p);
    });
    X.mount(nav, Object.keys(groups).map(function (g) {
      return X.h("div", null, [
        X.h("div.nav-group", { text: g }),
        X.h("div", null, groups[g].map(function (p) {
          return X.h("div.nav-item", {
            "data-key": p.key,
            onclick: function () { go(p.key); }
          }, [ X.icon(p.icon, 16), X.h("span", { text: p.title }) ]);
        }))
      ]);
    }));
  }

  function go(key) { location.hash = "#/" + key; }

  function setActive(key) {
    X.$$("#nav .nav-item").forEach(function (el) {
      el.classList.toggle("active", el.getAttribute("data-key") === key);
    });
  }

  /* ---------------------------------------------------------------- 路由 */
  function currentKey() {
    var h = (location.hash || "").replace(/^#\/?/, "");
    if (!h || !pageMap[h]) return PAGES.length ? PAGES[0].key : null;
    return h;
  }

  function renderPage(key) {
    var meta = META[key] || { title: key, desc: "" };
    var titleEl = X.$("#page-title");
    var descEl = X.$("#page-desc");
    if (titleEl) titleEl.textContent = meta.title;
    if (descEl) descEl.textContent = meta.desc;
    setActive(key);

    if (pageCleanup) { try { pageCleanup(); } catch (e) {} pageCleanup = null; }

    var view = X.$("#view");
    X.mount(view, X.loadingBlock("加载中…"));
    var fn = global.Pages && global.Pages[key];
    if (!fn) {
      X.mount(view, X.errorBlock(new Error("未找到页面：" + key)));
      return;
    }
    setTimeout(function () {
      try {
        var r = fn(view);
        if (typeof r === "function") pageCleanup = r;
      } catch (e) {
        X.mount(view, X.errorBlock(e));
      }
    }, 0);
  }

  function onRoute() { renderPage(currentKey()); }

  /* ---------------------------------------------------------------- 状态指示灯 */
  function setPill(id, kind, text) {
    var el = X.$("#" + id);
    if (!el) return;
    el.className = "pill is-" + kind;
    var t = X.$("#" + id + "-text");
    if (t) t.textContent = text;
  }

  function pingHealth() {
    X.api.get("/api/system/health").then(function (d) {
      var healthy = d && d.success && d.status === "healthy";
      setPill("health-pill", healthy ? "ok" : "danger",
              healthy ? "服务健康" : "服务异常");
    }).catch(function () {
      setPill("health-pill", "danger", "连接失败");
    });
  }

  function pingModel() {
    X.api.get("/api/model/status").then(function (d) {
      var loaded = d && (d.loaded === true);
      setPill("model-pill", loaded ? "ok" : "warn",
              loaded ? "模型已加载" : "模型未加载");
    }).catch(function () {
      setPill("model-pill", "warn", "模型未知");
    });
  }

  /* ---------------------------------------------------------------- 初始化 */
  function init() {
    renderNav();
    if (X.$("#sf-routers")) X.$("#sf-routers").textContent = (global.__APP__ || {}).routerCount || "-";
    if (X.$("#sf-endpoints")) X.$("#sf-endpoints").textContent = (global.__APP__ || {}).endpointCount || "-";

    X.$("#btn-refresh").addEventListener("click", function () { onRoute(); });
    X.$("#btn-menu").addEventListener("click", function () {
      X.$("#sidebar").classList.toggle("open");
    });
    X.$("#modal-close").addEventListener("click", function () { X.closeModal(); });
    X.$("#modal-mask").addEventListener("click", function (e) {
      if (e.target === this) X.closeModal();
    });

    window.addEventListener("hashchange", onRoute);
    pingHealth();
    pingModel();
    setInterval(pingHealth, 30000);
    setInterval(pingModel, 30000);

    onRoute();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
