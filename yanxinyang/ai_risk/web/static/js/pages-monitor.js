/* ==========================================================================
   pages-monitor.js —— 监控组：风控大盘 / 风险检查 / 评估历史
   ========================================================================== */
(function (global) {
  "use strict";
  var X = global.X, C = global.C, h = X.h;

  /* 颜色映射（直方图/环形图用） */
  var DECISION_COLOR = { "通过": "#16a34a", "标记": "#0891b2", "人工审核": "#d97706", "拒绝": "#dc2626" };
  var LEVEL_COLOR = { "低": "#16a34a", "中": "#0891b2", "高": "#d97706", "极高": "#dc2626" };
  var CASE_COLOR = { "待审核": "#d97706", "审核中": "#2563eb", "已通过": "#16a34a",
                     "已拒绝": "#dc2626", "已关闭": "#94a3b8" };

  function histToDonut(hist, colorMap) {
    return Object.keys(hist || {}).map(function (k) {
      return { label: k, value: hist[k], color: colorMap[k] || "#94a3b8" };
    });
  }

  /* ================================================================ 大盘 */
  function dashboard(view) {
    X.mount(view, X.loadingBlock("加载大盘数据…"));
    X.api.get("/api/dashboard/stats").then(function (d) {
      var data = d.data || {};
      var ov = data.overview || {};
      X.mount(view, buildDashboard(data, ov));
      bindTrend(view);
    }).catch(function (err) {
      X.mount(view, X.errorBlock(err, function () { dashboard(view); }));
    });
  }

  function buildDashboard(data, ov) {
    var frag = [];

    /* 告警 */
    var alerts = data.alerts || [];
    if (alerts.length) {
      alerts.forEach(function (a) {
        var kind = a.level === "严重" ? "danger" : "warn";
        frag.push(X.alert(kind, a.type + "：" + a.message, null));
      });
    }

    /* 核心指标统计卡（3 行 g6） */
    var s = function (label, value, opts) {
      return X.stat(label, value, opts || {});
    };
    frag.push(h("div.grid.g6.mb14", null, [
      s("累计评估", X.num(ov.total_assessments, 0), { icon: "gauge", tone: "info" }),
      s("累计事件", X.num(ov.total_events, 0), { icon: "history" }),
      s("今日事件", X.num(ov.today_events, 0), { icon: "bolt" }),
      s("平均融合分", X.num(ov.avg_final_score, 1), { tone: "warn" }),
      s("最高融合分", X.num(ov.max_final_score, 1), { tone: "danger" }),
      s("平均耗时", X.num(ov.avg_cost_ms, 1), { unit: "ms", icon: "reload" })
    ]));
    frag.push(h("div.grid.g6.mb14", null, [
      s("一票否决", X.num(ov.veto_count, 0), { tone: "danger", icon: "shield" }),
      s("否决率", X.pct(ov.veto_rate), { tone: "danger" }),
      s("规则命中率", X.pct(ov.rule_hit_rate), { tone: "ok" }),
      s("黑名单命中率", X.pct(ov.blacklist_hit_rate), { tone: "warn" }),
      s("启用规则", ov.rules_enabled + " / " + ov.rules_total, { icon: "rules" }),
      s("生效黑名单", X.num(ov.blacklist_total, 0), { icon: "ban" })
    ]));
    frag.push(h("div.grid.g6.mb14", null, [
      s("用户画像", X.num(ov.profiles_total, 0), { icon: "user" }),
      s("注册用户", X.num(ov.users_total, 0)),
      s("已标注样本", X.num(ov.labeled_samples, 0), { tone: "purple" }),
      s("待审核案件", X.num(ov.pending_cases, 0), { tone: "warn", icon: "inbox" }),
      s("进行中案件", X.num(ov.active_cases, 0), { tone: "info" }),
      s("窗口事件", X.num(ov.window_events, 0), { sub: "近 " + ov.window_hours + " 小时" })
    ]));

    /* 风险趋势（含天数切换） */
    var trendCard = X.card("风险趋势", null, {
      sub: "决策分布 · 按天",
      actions: h("div.row", { style: { gap: "6px" } }, ["7", "14", "30"].map(function (n) {
        return h("button.btn.btn-sm.trend-btn" + (n === "14" ? ".btn-primary" : ""),
          { "data-days": n, text: n + " 天" });
      })),
      cls: "mb14"
    });
    trendCard.querySelector(".card-body").appendChild(h("div#trend-chart"));
    frag.push(trendCard);

    /* 四张分布图 */
    frag.push(h("div.grid.g2.mb14", null, [
      distCard("决策分布", C.donut(histToDonut(data.decision_histogram, DECISION_COLOR))),
      distCard("风险等级分布", C.donut(histToDonut(data.risk_level_histogram, LEVEL_COLOR)))
    ]));
    frag.push(h("div.grid.g2.mb14", null, [
      distCard("事件类型分布",
        C.bar(Object.keys(data.event_type_histogram || {}),
              Object.values(data.event_type_histogram || {}),
              { colors: Object.keys(data.event_type_histogram || {}).map(function (_, i) {
                  return C.PALETTE[i % C.PALETTE.length];
                }) })),
      distCard("案件状态分布", C.donut(histToDonut(data.case_status_histogram, CASE_COLOR)))
    ]));

    /* TOP 规则 + TOP 风险用户 */
    frag.push(h("div.grid.g2.mb14", null, [
      topRulesCard(data.top_rules),
      topUsersCard(data.top_risk_users)
    ]));

    /* 最近评估 */
    frag.push(recentCard(data.recent_assessments));
    return frag;
  }

  function distCard(title, chart) {
    var c = X.card(title, null, { cls: "mb0" });
    c.querySelector(".card-body").appendChild(chart);
    return c;
  }

  function topRulesCard(rules) {
    var rows = (rules || []).map(function (r) {
      return { rule_id: r.rule_id, rule_name: r.rule_name, risk_level: r.risk_level,
               hit_count: r.hit_count };
    });
    var c = X.card("命中 TOP 规则", null, { cls: "mb0" });
    c.querySelector(".card-body").appendChild(X.table(
      [ { key: "rule_id", label: "规则 ID", width: "84px" },
        { key: "rule_name", label: "名称", render: function (r) {
            return h("span", null, [ r.rule_name, " ", X.levelTag(r.risk_level) ]); } },
        { key: "hit_count", label: "命中", align: "right", cls: "num",
          render: function (r) { return X.num(r.hit_count, 0); } } ],
      rows, { emptyText: "暂无规则命中" }));
    return c;
  }

  function topUsersCard(users) {
    var rows = (users || []).map(function (u) {
      return { user_id: u.user_id, user_name: u.user_name, max_final_score: u.max_final_score,
               risk_event_count: u.risk_event_count };
    });
    var c = X.card("高危用户 TOP", null, { cls: "mb0" });
    c.querySelector(".card-body").appendChild(X.table(
      [ { key: "user_id", label: "用户", width: "84px" },
        { key: "user_name", label: "昵称" },
        { key: "max_final_score", label: "最高分", align: "right", cls: "num",
          render: function (r) {
            return h("span" + (X.scoreClass(r.max_final_score).replace("c-", ".c-")),
              { text: X.num(r.max_final_score, 0) }); } },
        { key: "risk_event_count", label: "高危事件", align: "right", cls: "num",
          render: function (r) { return X.num(r.risk_event_count, 0); } } ],
      rows, { emptyText: "暂无用户数据" }));
    return c;
  }

  function recentCard(rows) {
    var c = X.card("最近评估", null, { cls: "mb0" });
    var body = c.querySelector(".card-body");
    body.appendChild(X.table(
      [ { key: "create_time", label: "时间", width: "140px", render: function (r) {
            return X.h("span.mut.f-12", { text: X.dt(r.create_time, "short") }); } },
        { key: "user_id", label: "用户", width: "84px" },
        { key: "event_type", label: "事件", width: "80px" },
        { key: "final_score", label: "融合分", align: "right", cls: "num", width: "76px",
          render: function (r) {
            return h("span" + (X.scoreClass(r.final_score).replace("c-", ".c-")),
              { text: X.num(r.final_score, 0) }); } },
        { key: "decision", label: "决策", width: "84px", render: function (r) {
            return X.decisionTag(r.decision); } },
        { key: "is_veto", label: "否决", width: "56px", align: "center",
          render: function (r) {
            return r.is_veto ? X.tag("否决", "red", "tag-dot") : h("span.mut2", { text: "-" }); } } ],
      rows || [], { onRowClick: function (r) { location.hash = "#/assessment?id=" + r.assessment_id; },
                    emptyText: "暂无评估记录" }));
    return c;
  }

  function bindTrend(view) {
    var chartEl = X.$("#trend-chart");
    if (!chartEl) return;
    function load(days) {
      X.mount(chartEl, X.loadingBlock("加载趋势…"));
      X.api.get("/api/dashboard/trend", { days: days }).then(function (d) {
        var series = d.series || [];
        X.mount(chartEl, buildTrend(series));
      }).catch(function (err) {
        X.mount(chartEl, X.errorBlock(err, function () { load(days); }));
      });
    }
    X.$$(".trend-btn", view).forEach(function (b) {
      b.addEventListener("click", function () {
        X.$$(".trend-btn", view).forEach(function (x) { x.classList.remove("btn-primary"); });
        b.classList.add("btn-primary");
        load(parseInt(b.getAttribute("data-days"), 10));
      });
    });
    load(14);
  }

  function buildTrend(series) {
    if (!series.length) return X.emptyBlock("近 30 天暂无数据");
    var labels = series.map(function (s) { return s.date.slice(5); });
    var sers = [
      { name: "拒绝", data: series.map(function (s) { return s["拒绝"]; }),
        color: DECISION_COLOR["拒绝"] },
      { name: "人工审核", data: series.map(function (s) { return s["人工审核"]; }),
        color: DECISION_COLOR["人工审核"] },
      { name: "标记", data: series.map(function (s) { return s["标记"]; }),
        color: DECISION_COLOR["标记"] },
      { name: "通过", data: series.map(function (s) { return s["通过"]; }),
        color: DECISION_COLOR["通过"] }
    ];
    return C.line(labels, sers, {
      height: 260, legend: true,
      formatValue: function (v) { return X.num(v, 0); }
    });
  }

  /* ================================================================ 风险检查 */
  function check(view) {
    var wrap = h("div");
    var formCard = X.card("风险检查请求", null, {
      sub: "七步流水线入口",
      actions: h("button.btn.btn-primary.btn-sm", { id: "btn-run-check", onclick: run },
        [ X.icon("play", 13), "开始检查" ])
    });
    var fb = formCard.querySelector(".card-body");
    var fEvent = X.input({ value: "考试" });
    var fUser = X.input({ placeholder: "如 1001", value: "1001" });
    var fSource = X.input({ placeholder: "如 ORD10010001", value: "ORD10010001" });
    var fOrder = X.input({ placeholder: "可选，同事件源" });
    var fAmount = X.input({ type: "number", placeholder: "可选，与学习记录一致" });
    var fIp = X.input({ placeholder: "可选 8.8.8.8" });
    var fDevice = X.input({ placeholder: "可选 D0001" });
    var fRemark = X.input({ placeholder: "可选备注" });
    fb.appendChild(h("div.form-row", null, [
      fieldCell("事件类型", X.select(
        ["考试", "作业", "选课", "成绩申诉"].map(function (x) { return { value: x, label: x }; }),
        { value: "考试" }), fEvent),
      fieldCell("用户 ID", fUser),
      fieldCell("事件源 ID", fSource)
    ]));
    fb.appendChild(h("div.form-row", null, [
      fieldCell("学习记录 ID", fOrder),
      fieldCell("投入金额", fAmount),
      fieldCell("客户端 IP", fIp)
    ]));
    fb.appendChild(h("div.form-row", null, [
      fieldCell("设备 ID", fDevice),
      fieldCell("备注", fRemark)
    ]));
    wrap.appendChild(formCard);

    var resultCard = X.card("检查结果", null, { cls: "mt14 mb0" });
    resultCard.querySelector(".card-body").appendChild(
      h("div.mut.f-12", { text: "填写请求后点击「开始检查」，将跑完 7 步流水线并展示完整过程。" }));
    wrap.appendChild(resultCard);

    X.mount(view, wrap);

    function fieldCell(label, ctrl) {
      return h("div.field", null, [ h("label.label", { text: label }), ctrl ]);
    }

    function run() {
      var body = {
        event_type: fEvent.value || "考试",
        user_id: fUser.value.trim(),
        source_id: fSource.value.trim(),
        operator: "运营"
      };
      ["order_id", "amount", "client_ip", "device_id", "remark"].forEach(function (k, i) {
        var v = [fOrder, fAmount, fIp, fDevice, fRemark][i].value.trim();
        if (v !== "") body[k] = (k === "amount") ? Number(v) : v;
      });
      if (!body.user_id || !body.source_id) {
        X.toast.warn("请填写用户 ID 与事件源 ID");
        return;
      }
      var btn = X.$("#btn-run-check");
      if (btn) { btn.disabled = true; btn.textContent = "检查中…"; }
      var rb = resultCard.querySelector(".card-body");
      X.mount(rb, X.loadingBlock("正在执行 7 步流水线…"));
      X.api.post("/api/risk/check", body).then(function (d) {
        renderCheckResult(rb, d.data);
      }).catch(function (err) {
        X.mount(rb, X.errorBlock(err, run));
      }).then(function () {
        if (btn) { btn.disabled = false; btn.textContent = ""; btn.appendChild(X.icon("play", 13));
          btn.appendChild(document.createTextNode(" 开始检查")); }
      });
    }
  }

  function renderCheckResult(rb, r) {
    var frag = [];

    /* 裁决卡 */
    frag.push(buildVerdict(r));

    /* 流水线时间线 */
    frag.push(buildPipeline(r.timeline));

    /* 校验轨迹 */
    frag.push(buildChecks(r.validate_checks));

    /* 双轨融合步骤 */
    frag.push(buildFusion(r));

    /* 25 维特征 */
    frag.push(buildFeatures(r.features, r.feature_defs));

    /* 命中规则 + 黑名单 */
    frag.push(buildHitRules(r));

    X.mount(rb, frag);
  }

  function buildVerdict(r) {
    var cls = "d-" + (X.DECISION_KEY[r.decision] || "mark");
    var card = h("div.card.verdict." + cls);
    var head = h("div.card-head", null, [
      h("h3", { text: "风控裁决" }),
      h("span.spacer"),
      X.tag("cost " + r.cost_ms + "ms", "gray")
    ]);
    var body = h("div.card-body", null, [
      h("div.vd-main", null, [
        h("div.vd-score", null, [
          h("b", { text: String(Math.round(r.final_score)) }),
          h("i", { text: " 融合分" })
        ]),
        h("div.vd-right", null, [
          h("div.vd-title", null, [ X.decisionTag(r.decision),
            r.is_veto ? X.tag("一票否决", "red", "tag-dot") : null ]),
          h("div.vd-reason", { text: r.reason || "" })
        ])
      ]),
      h("div.row.mt10", { style: { gap: "10px", flexWrap: "wrap" } }, [
        X.tag("风险等级：" + r.risk_level, (X.LEVEL_KEY[r.risk_level] || "gray"), "tag-dot"),
        X.tag("规则分 " + X.num(r.rule_score, 1), "blue"),
        X.tag("模型分 " + X.num(r.ml_score, 1) + (r.ml_loaded ? "" : "（未加载）"), "purple"),
        X.tag("融合分 " + X.num(r.fused_score, 1), "cyan"),
        X.tag("标签 " + r.label + "（" + r.label_source + "）", "gray")
      ])
    ]);
    card.appendChild(head); card.appendChild(body);
    return card;
  }

  function buildPipeline(timeline) {
    var card = X.card("七步流水线", null, { sub: "单事务 · 全过或全不过", cls: "mt14 mb0" });
    var body = card.querySelector(".card-body");
    var list = h("div.pipeline");
    (timeline || []).forEach(function (t, i) {
      list.appendChild(h("div.pl-step", null, [
        h("div.pl-no", { text: (i + 1) }),
        h("div.pl-body", null, [
          h("div.pl-name", { text: t.name }),
          h("div.pl-ms", { text: t.detail }),
          h("div.pl-detail", { text: "耗时 " + t.elapsed_ms + "ms" })
        ])
      ]));
    });
    body.appendChild(list);
    return card;
  }

  function buildChecks(checks) {
    var card = X.card("请求校验（6 个 ensure_*）", null, { cls: "mt14 mb0" });
    var body = card.querySelector(".card-body");
    var list = h("div.checks");
    (checks || []).forEach(function (c) {
      var ok = c.result === "通过";
      list.appendChild(h("div.check-item", null, [
        h("span.ci-icon" + (ok ? ".is-ok" : ".is-skip"), null,
          ok ? X.icon("check", 13) : X.icon("info", 13)),
        h("div.ci-text", null, [
          h("div.ci-name", { text: c.step }),
          h("div.ci-desc", { text: (c.detail || "") })
        ]),
        h("span.ci-tag" + (ok ? ".tag-green" : ".tag-gray"),
          { text: c.result, class: "tag" })
      ]));
    });
    body.appendChild(list);
    return card;
  }

  function buildFusion(r) {
    var card = X.card("双轨融合 + 一票否决", null, { cls: "mt14 mb0" });
    var body = card.querySelector(".card-body");
    var steps = r.fusion_steps || [];
    var wrap = h("div.fusion");
    steps.forEach(function (st) {
      var veto = st.triggered;
      wrap.appendChild(h("div.fu-step" + (veto ? ".is-veto" : ""), null, [
        h("div.fu-no", { text: st.step }),
        h("div.fu-body", null, [
          h("div.fu-name", { text: st.name }),
          st.formula ? h("div.fu-formula", { text: st.formula }) : null,
          h("div.fu-out", { text: "= " + X.num(st.value, 2) + (veto ? "  ⚑ 否决触发" : "") })
        ])
      ]));
    });
    body.appendChild(wrap);
    /* 权重条 */
    var degraded = !r.ml_loaded;
    var wr = r.weight_rule != null ? r.weight_rule : 0.5;
    var wm = r.weight_ml != null ? r.weight_ml : 0.5;
    if (degraded) { wr = 1.0; wm = 0.0; }
    body.appendChild(h("div.weights" + (degraded ? ".w-zero" : ""), null, [
      h("div.w-rule", null, [ h("span", { text: "规则权重 α" }), h("b", { text: wr.toFixed(2) }) ]),
      h("div.w-ml", null, [ h("span", { text: "模型权重 β" }), h("b", { text: wm.toFixed(2) }) ]),
      degraded ? h("span.tag.tag-orange", { text: "模型未加载 → 纯规则模式" }) : null
    ]));
    return card;
  }

  function buildFeatures(features, defs) {
    var card = X.card("25 维特征", null, { sub: "用户 14 + 学习 8 + 账号 3", cls: "mt14 mb0" });
    var body = card.querySelector(".card-body");
    var map = {};
    (defs || []).forEach(function (f) { map[f.name] = f; });
    var hits = {};
    (features || {}); // no hit info in check result; mark none
    var grid = h("div.feat-grid");
    Object.keys(features || {}).forEach(function (name) {
      var def = map[name] || { name: name, dim: "用户", label: name };
      var val = features[name];
      grid.appendChild(h("div.feat" + (hits[name] ? ".is-hit" : ""), null, [
        h("div.feat-head", null, [
          h("span.feat-name", { text: name, title: name }),
          X.tag(shortDim(def.dim), (X.DIM_TAG[def.dim] || "gray"))
        ]),
        h("div.feat-val", { text: X.num(val, 2) }),
        h("div.feat-label", { text: def.label || name })
      ]));
    });
    body.appendChild(grid);
    return card;
  }

  function dimClass(dim) {
    return dim === "学习" ? "order" : dim === "账号" ? "addr" : "user";
  }
  function shortDim(dim) {
    return dim === "用户" ? "U" : dim === "学习" ? "O" : dim === "账号" ? "A" : dim;
  }

  function buildHitRules(r) {
    var frag = [];
    var hits = r.hit_rules || [];
    var card = X.card("命中规则（" + hits.length + "）", null, { cls: "mt14 mb0" });
    var body = card.querySelector(".card-body");
    if (!hits.length) {
      body.appendChild(X.emptyBlock("本次检查未命中任何规则"));
    } else {
      var list = h("div.hits");
      hits.forEach(function (hr) {
        var lv = hr.risk_level || "中";
        list.appendChild(h("div.hit.lv-" + (X.LEVEL_KEY[lv] || "mid"), null, [
          h("div.hit-head", null, [
            h("span.hit-id", { text: hr.rule_id }),
            h("span.hit-name", { text: hr.rule_name }),
            hr.is_blacklist ? X.tag("黑名单", "red", "tag-dot") : null,
            h("span.spacer"),
            X.tag("分 " + X.num(hr.risk_score, 0), (X.LEVEL_KEY[lv] || "gray"), "tag-dot"),
            X.tag(hr.action, "gray")
          ]),
          hr.description ? h("div.hit-desc", { text: hr.description }) : null
        ]));
      });
      body.appendChild(list);
    }
    frag.push(card);

    /* 黑名单命中 */
    var bl = r.blacklist_hits || [];
    if (bl.length) {
      var bc = X.card("黑名单命中（" + bl.length + "）", null, { cls: "mt14 mb0" });
      var bb = bc.querySelector(".card-body");
      bb.appendChild(X.table(
        [ { key: "rule_name", label: "类型" },
          { key: "risk_level", label: "等级", width: "80px", render: function (x) {
              return X.levelTag(x.risk_level); } },
          { key: "description", label: "说明" } ],
        bl, { empty: false }));
      frag.push(bc);
    }
    return h("div", null, frag);
  }

  /* ================================================================ 评估历史 */
  function assessment(view) {
    var params = parseQuery(location.hash);
    if (params.id) { renderAssessmentDetail(view, params.id); return; }
    renderAssessmentList(view);
  }

  function parseQuery(hash) {
    var q = {};
    var i = hash.indexOf("?");
    if (i < 0) return q;
    hash.slice(i + 1).split("&").forEach(function (kv) {
      var p = kv.split("=");
      if (p[0]) q[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || "");
    });
    return q;
  }

  function renderAssessmentList(view) {
    var state = { limit: 20, offset: 0, filters: {} };
    function load() {
      X.mount(view, X.loadingBlock("加载评估历史…"));
      var qs = Object.assign({ limit: state.limit, offset: state.offset }, state.filters);
      X.api.get("/api/risk/assessments", qs).then(function (d) {
        X.mount(view, buildList(d, state, load));
      }).catch(function (err) {
        X.mount(view, X.errorBlock(err, load));
      });
    }
    load();
  }

  function buildList(d, state, load) {
    var frag = [];
    var fb = X.filterBar([
      { key: "user_id", label: "用户 ID", placeholder: "U0001" },
      { key: "decision", label: "决策", type: "select",
        options: ["", "通过", "标记", "人工审核", "拒绝"].map(function (x) {
          return { value: x, label: x || "全部" }; }) },
      { key: "risk_level", label: "风险等级", type: "select",
        options: ["", "低", "中", "高", "极高"].map(function (x) {
          return { value: x, label: x || "全部" }; }) },
      { key: "keyword", label: "关键字", placeholder: "评估/事件源 ID" }
    ], function (vals) {
      state.filters = {}; Object.keys(vals).forEach(function (k) { state.filters[k] = vals[k]; });
      state.offset = 0; load();
    });
    frag.push(fb.el);
    frag.push(h("div.mt14"));
    var card = X.card("评估记录", null, {
      sub: "共 " + X.num(d.total, 0) + " 条", cls: "mb0 mt10" });
    var body = card.querySelector(".card-body");
    body.appendChild(X.table(
      [ { key: "create_time", label: "时间", width: "140px",
          render: function (r) { return h("span.mut.f-12", { text: X.dt(r.create_time, "short") }); } },
        { key: "assessment_id", label: "评估 ID", width: "200px",
          render: function (r) { return h("span.chip", { text: r.assessment_id }); } },
        { key: "user_id", label: "用户", width: "84px" },
        { key: "event_type", label: "事件", width: "84px" },
        { key: "final_score", label: "融合分", align: "right", cls: "num", width: "76px",
          render: function (r) {
            return h("span" + (X.scoreClass(r.final_score).replace("c-", ".c-")),
              { text: X.num(r.final_score, 0) }); } },
        { key: "risk_level", label: "等级", width: "70px", render: function (r) {
            return X.levelTag(r.risk_level); } },
        { key: "decision", label: "决策", width: "84px", render: function (r) {
            return X.decisionTag(r.decision); } },
        { key: "hit_rule_count", label: "命中", align: "right", cls: "num", width: "60px",
          render: function (r) { return X.num(r.hit_rule_count, 0); } },
        { key: "is_veto", label: "否决", width: "56px", align: "center",
          render: function (r) {
            return r.is_veto ? X.tag("否决", "red", "tag-dot") : h("span.mut2", { text: "-" }); } } ],
      d.items || [], { onRowClick: function (r) { location.hash = "#/assessment?id=" + r.assessment_id; },
                        emptyText: "暂无评估记录" }));
    body.appendChild(X.pager(d.total, state.limit, state.offset, function (off) {
      state.offset = off; load();
    }));
    frag.push(card);
    return frag;
  }

  function renderAssessmentDetail(view, id) {
    X.mount(view, X.loadingBlock("加载评估详情…"));
    X.api.get("/api/risk/assessments/" + encodeURIComponent(id)).then(function (d) {
      // feature_defs 由后端挂在 data 内（与 /api/risk/check 一致），顶层兼容兜底
      var detail = d.data || {};
      X.mount(view, buildDetail(detail, detail.feature_defs || d.feature_defs, id));
    }).catch(function (err) {
      X.mount(view, X.errorBlock(err, function () { renderAssessmentDetail(view, id); }));
    });
  }

  function buildDetail(r, defs, id) {
    var frag = [];
    frag.push(h("div.row.mb14", null, [
      h("button.btn.btn-sm", { onclick: function () { location.hash = "#/assessment"; } },
        [ X.icon("chevR", 13), "返回列表" ]),
      h("span.spacer"),
      X.tag(id, "gray")
    ]));
    /* 摘要卡 */
    var card = X.card("评估摘要", null, { cls: "mb14" });
    var b = card.querySelector(".card-body");
    b.appendChild(X.kv([
      [ "决策", X.decisionTag(r.decision) ],
      [ "风险等级", X.levelTag(r.risk_level) ],
      [ "融合分", h("b" + (X.scoreClass(r.final_score).replace("c-", ".c-")),
          { text: X.num(r.final_score, 1) }) ],
      [ "规则分 / 模型分", X.num(r.rule_score, 1) + " / " +
        (r.ml_loaded ? X.num(r.ml_score, 1) : "未加载") ],
      [ "一票否决", r.is_veto ? X.tag("是", "red", "tag-dot") : "否" ],
      [ "案件", r.case ? X.caseTag(r.case.case_status) : "未生成" ],
      [ "用户 / 事件", r.user_id + " · " + r.event_type ],
      [ "创建时间", X.dt(r.create_time) ]
    ], { two: true }));
    b.appendChild(h("div.mt10.alert.alert-info", null, [
      X.icon("info", 16), h("div", null, [ h("b", { text: "决策依据" }), r.reason || "-" ]) ]));
    frag.push(card);

    /* 命中规则 */
    frag.push(buildHitRules({ hit_rules: r.hit_rules || [], blacklist_hits: [] }));

    /* 25 维特征快照 */
    frag.push(buildFeatureSnapshot(r.features || [], r.feature_snapshot || {}, defs));
    return frag;
  }

  function buildFeatureSnapshot(rows, snapshot, defs) {
    var card = X.card("25 维特征快照", null, { sub: "来自 risk_feature 落库", cls: "mt14 mb0" });
    var body = card.querySelector(".card-body");
    var map = {};
    (defs || []).forEach(function (f) { map[f.name] = f; });
    if (!rows.length && snapshot && typeof snapshot === "object") {
      rows = Object.keys(snapshot).map(function (k) {
        return { feature_name: k, feature_value: snapshot[k], feature_dim: (map[k] || {}).dim };
      });
    }
    var grid = h("div.feat-grid");
    rows.forEach(function (fr) {
      var def = map[fr.feature_name] || { label: fr.feature_name, dim: fr.feature_dim };
      grid.appendChild(h("div.feat", null, [
        h("div.feat-head", null, [
          h("span.feat-name", { text: fr.feature_name, title: fr.feature_name }),
          X.tag(shortDim(def.dim || fr.feature_dim), (X.DIM_TAG[def.dim || fr.feature_dim] || "gray"))
        ]),
        h("div.feat-val", { text: X.num(fr.feature_value, 2) }),
        h("div.feat-label", { text: def.label || fr.feature_name })
      ]));
    });
    body.appendChild(grid);
    return card;
  }

  /* 注册 */
  global.Pages = global.Pages || {};
  global.Pages["dashboard"] = dashboard;
  global.Pages["check"] = check;
  global.Pages["assessment"] = assessment;
})(window);
