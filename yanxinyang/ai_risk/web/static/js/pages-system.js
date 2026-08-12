/* ==========================================================================
   pages-system.js —— 系统组：模型中心 / 系统配置 / 审计日志
   ========================================================================== */
(function (global) {
  "use strict";
  var X = global.X, C = global.C, h = X.h;

  /* ================================================================ 模型中心 */
  function modelPage(view) {
    var state = { limit: 20, offset: 0, filters: {} };
    function load() {
      X.mount(view, X.loadingBlock("加载模型状态…"));
      X.api.get("/api/model/status").then(function (d) {
        X.mount(view, buildModel(d, load));
      }).catch(function (err) {
        X.mount(view, X.errorBlock(err, load));
      });
    }
    load();
  }

  function buildModel(d, load) {
    var frag = [];
    var loaded = !!d.loaded;
    frag.push(X.alert(loaded ? "ok" : "warn",
      loaded ? "模型已加载（双轨融合启用）" : "模型未加载（降级为纯规则模式）",
      "XGBoost · " + (d.implementation || "—") + " · 特征维度 " + (d.feature_count || 25)));

    /* 核心指标 */
    var grid = h("div.metric-grid.mb14");
    [ ["已加载", loaded ? "是" : "否", loaded],
      ["启用", d.enabled ? "是" : "否", d.enabled],
      ["决策树", X.num(d.trees, 0)],
      ["最佳迭代", X.num(d.best_iteration, 0)],
      ["F1 阈值", X.num(d.best_f1_threshold, 3)],
      ["训练于", d.trained_at ? X.dt(d.trained_at, "date") : "—"],
      ["模型路径", d.model_path ? X.trunc(d.model_path, 22) : "—"],
      ["特征维度", X.num(d.feature_count, 0)]
    ].forEach(function (m) {
      grid.appendChild(h("div.metric" + (m[2] ? ".is-good" : ""), null, [
        h("div.metric-name", { text: m[0] }),
        h("div.metric-val", { text: String(m[1]) })
      ]));
    });
    frag.push(grid);

    /* 样本与训练 */
    var td = d.training_data || {};
    var trainCard = X.card("训练样本", null, {
      sub: td.ready ? "样本充足，可训练" : "样本不足", cls: "mb14" });
    var tb = trainCard.querySelector(".card-body");
    tb.appendChild(X.kv([
      [ "已标注样本", X.num(td.labeled_samples, 0) ],
      [ "正样本", X.num(td.positive_samples, 0) ],
      [ "正样本占比", X.pct(td.positive_ratio) ],
      [ "最少需要", X.num(td.min_required, 0) ],
      [ "特征快照数", X.num(td.feature_snapshots, 0) ],
      [ "是否就绪", td.ready ? X.tag("就绪", "green") : X.tag("不足", "orange") ]
    ], { two: true }));
    if (td.hint) tb.appendChild(h("div.mt10.alert.alert-info", null,
      [ X.icon("info", 16), h("div", null, td.hint) ]));
    if (td.label_sources) {
      var src = Object.keys(td.label_sources).map(function (k) {
        return X.tag(k + " " + td.label_sources[k], "gray"); });
      tb.appendChild(h("div.mt10.row", { style: { gap: "6px", flexWrap: "wrap" } }, src));
    }
    frag.push(trainCard);

    /* 参数 / 阈值 / 融合 */
    frag.push(h("div.grid.g3.mb14", null, [
      kvCard("超参数", d.params),
      kvCard("决策阈值", d.decision_thresholds),
      kvCard("双轨融合", d.fusion)
    ]));

    /* 特征重要性 */
    frag.push(buildImportance());

    /* 操作 */
    frag.push(h("div.row.mb14", null, [
      h("button.btn.btn-primary.btn-sm", { text: "重新加载模型",
        onclick: function () { doReload("reload", load); } }),
      h("button.btn.btn-sm", { text: "卸载模型（纯规则）",
        onclick: function () { doReload("unload", load); } })
    ]));
    return frag;
  }

  function kvCard(title, obj) {
    var card = X.card(title, null, { cls: "mb0" });
    var body = card.querySelector(".card-body");
    if (!obj || typeof obj !== "object") { body.appendChild(X.emptyBlock("—")); return card; }
    var pairs = Object.keys(obj).map(function (k) {
      return [ k, (obj[k] === null || obj[k] === undefined || obj[k] === "") ? "—" :
        (typeof obj[k] === "object" ? JSON.stringify(obj[k]) : String(obj[k])) ];
    });
    body.appendChild(X.kv(pairs, { two: true }));
    return card;
  }

  function buildImportance() {
    var card = X.card("特征重要性（weight / gain / cover）", null, { cls: "mb0" });
    var body = card.querySelector(".card-body");
    var box = h("div", null, X.loadingBlock("加载特征重要性…"));
    body.appendChild(box);
    X.api.get("/api/model/importance").then(function (d) {
      // 后端 /api/model/importance 是扁平结构：weight / gain / cover 在顶层
      var imp = d.importance || d;
      if (d.available === false || !imp.weight || !imp.weight.length) {
        X.mount(box, X.alert("warn", "模型未加载", "加载模型后可查看 3 种特征重要性"));
        return;
      }
      X.mount(box, h("div.grid.g3", null, [
        hbarCard("weight（分裂次数）", imp.weight, "#2563eb"),
        hbarCard("gain（信息增益）", imp.gain, "#7c3aed"),
        hbarCard("cover（覆盖样本）", imp.cover, "#0891b2")
      ]));
    }).catch(function (err) {
      X.mount(box, X.errorBlock(err));
    });
    return card;
  }

  function hbarCard(title, arr, color) {
    var c = X.card(title, null, { cls: "mb0" });
    var b = c.querySelector(".card-body");
    if (!arr || !arr.length) { b.appendChild(X.emptyBlock("无数据")); return c; }
    var items = arr.map(function (f) {
      return { label: f.feature, value: f.value, color: color };
    });
    b.appendChild(C.hbar(items, { formatValue: X.num }));
    return c;
  }

  function doReload(action, load) {
    X.confirmModal({
      title: action === "reload" ? "重新加载模型" : "卸载模型",
      message: action === "reload"
        ? "将重新加载 XGBoost 模型并启用双轨融合，确定？"
        : "将卸载模型并降级为纯规则模式，确定？",
      okText: action === "reload" ? "重新加载" : "卸载", danger: action === "unload"
    }).then(function (ok) {
      if (!ok) return;
      X.api.post("/api/model/reload", { action: action, operator: "admin" })
        .then(function (r) { X.toast.ok(r.message || "操作完成"); load(); })
        .catch(function (err) { X.toast.err(err.message); });
    });
  }

  /* ================================================================ 系统配置 */
  function configPage(view) {
    X.mount(view, X.loadingBlock("加载配置…"));
    X.api.get("/api/system/config").then(function (d) {
      X.mount(view, buildConfig(d));
    }).catch(function (err) {
      X.mount(view, X.errorBlock(err, function () { configPage(view); }));
    });
  }

  function buildConfig(d) {
    var frag = [];
    frag.push(X.alert("info", "本页只读", (d.notes && d.notes.readonly) ||
      "修改请编辑项目根目录 .env 后重启服务"));
    var groups = d.groups || {};
    Object.keys(groups).forEach(function (gName) {
      var rows = groups[gName] || [];
      var wrap = h("div.cfg-group");
      wrap.appendChild(h("div.cfg-title", null, [
        h("span", { text: gName }),
        h("span.cnt", { text: rows.length + " 项" })
      ]));
      var table = X.table(
        [ { key: "label", label: "配置项", width: "220px", render: function (r) {
            return h("span", null, [ r.label, " ", h("code", { text: r.field }) ]); } },
          { key: "value", label: "值", render: function (r) {
            return h("b", { text: String(r.value) }); } },
          { key: "note", label: "说明", render: function (r) {
            return r.note ? h("span.mut.f-12", { text: r.note }) : h("span.mut2", { text: "-" }); } } ],
        rows, { empty: false });
      wrap.appendChild(table);
      frag.push(wrap);
    });

    if (d.paths) {
      frag.push(h("div.cfg-group", null, [
        h("div.cfg-title", null, [ h("span", { text: "关键路径" }) ]),
        kvCardLite([ ["数据库", d.paths.database], ["模型", d.paths.model], ["日志", d.paths.log] ])
      ]));
    }
    return frag;
  }

  function kvCardLite(pairs) {
    var c = X.card(null, null, { cls: "mb0" });
    c.querySelector(".card-body").appendChild(X.kv(pairs, { two: true }));
    return c;
  }

  /* ================================================================ 审计日志 */
  function auditPage(view) {
    var state = { limit: 50, offset: 0, filters: {} };
    function load() {
      X.mount(view, X.loadingBlock("加载审计日志…"));
      var qs = Object.assign({ limit: state.limit, offset: state.offset }, state.filters);
      X.api.get("/api/system/audit-logs", qs).then(function (d) {
        X.mount(view, buildAudit(d, state, load));
      }).catch(function (err) {
        X.mount(view, X.errorBlock(err, load));
      });
    }
    load();
  }

  function buildAudit(d, state, load) {
    var frag = [];
    var typeStats = d.target_type_stats || {};
    var opStats = d.operator_stats || {};
    var fb = X.filterBar([
      { key: "target_type", label: "对象类型", type: "select",
        options: [""].concat(Object.keys(typeStats)).map(function (x) {
          return { value: x, label: x || "全部" }; }) },
      { key: "operator", label: "操作人", type: "select",
        options: [""].concat(Object.keys(opStats)).map(function (x) {
          return { value: x, label: x || "全部" }; }) }
    ], function (vals) {
      state.filters = {}; Object.keys(vals).forEach(function (k) { state.filters[k] = vals[k]; });
      state.offset = 0; load();
    });
    frag.push(fb.el);
    frag.push(h("div.mt14"));

    frag.push(h("div.row.mb10", null, [
      X.tag("共 " + X.num(d.total, 0) + " 条", "gray"),
      X.tag("对象类型 " + Object.keys(typeStats).length, "blue"),
      X.tag("操作人 " + Object.keys(opStats).length, "purple")
    ]));

    var card = X.card(null, null, { cls: "mb0 mt10" });
    var body = card.querySelector(".card-body");
    body.appendChild(X.table(
      [ { key: "create_time", label: "时间", width: "140px",
          render: function (r) { return h("span.mut.f-12", { text: X.dt(r.create_time, "short") }); } },
        { key: "operator", label: "操作人", width: "90px" },
        { key: "action_type", label: "动作", width: "130px" },
        { key: "target_type", label: "对象", width: "70px" },
        { key: "target_id", label: "对象 ID", width: "200px",
          render: function (r) { return r.target_id ? h("span.chip", { text: r.target_id }) : h("span.mut2", { text: "-" }); } },
        { key: "diff", label: "变更", render: function (r) {
            var before = r.before_value, after = r.after_value;
            if (!before && !after) return h("span.mut2", { text: r.remark || "-" });
            return h("div.audit-diff", null, [
              before ? h("div.audit-col.before", null, [ h("h4", { text: "变更前" }),
                X.jsonBlock(typeof before === "string" ? before : before, true) ]) : null,
              after ? h("div.audit-col.after", null, [ h("h4", { text: "变更后" }),
                X.jsonBlock(typeof after === "string" ? after : after, true) ]) : null
            ]);
          } } ],
      d.items || [], { emptyText: "暂无审计记录", compact: true }));
    body.appendChild(X.pager(d.total, state.limit, state.offset, function (off) {
      state.offset = off; load();
    }));
    frag.push(card);
    return frag;
  }

  /* 注册 */
  global.Pages = global.Pages || {};
  global.Pages["model"] = modelPage;
  global.Pages["config"] = configPage;
  global.Pages["audit"] = auditPage;
})(window);
