/* ==========================================================================
   pages-handle.js —— 处置组：案件中心 / 规则引擎 / 黑名单
   ========================================================================== */
(function (global) {
  "use strict";
  var X = global.X, h = X.h;

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

  /* 命中规则渲染（通用） */
  function renderHitRules(hits, title) {
    var card = X.card(title || "命中规则（" + (hits || []).length + "）", null, { cls: "mb0" });
    var body = card.querySelector(".card-body");
    if (!hits || !hits.length) {
      body.appendChild(X.emptyBlock("未命中任何规则"));
      return card;
    }
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
    return card;
  }

  /* ================================================================ 案件中心 */
  function casePage(view) {
    var q = parseQuery(location.hash);
    if (q.id) { renderCaseDetail(view, q.id); return; }
    renderCaseList(view);
  }

  function renderCaseList(view) {
    var state = { limit: 20, offset: 0, filters: {} };
    function load() {
      X.mount(view, X.loadingBlock("加载案件列表…"));
      var qs = Object.assign({ limit: state.limit, offset: state.offset }, state.filters);
      X.api.get("/api/cases", qs).then(function (d) {
        X.mount(view, buildCaseList(d, state, load));
      }).catch(function (err) {
        X.mount(view, X.errorBlock(err, load));
      });
    }
    load();
  }

  function buildCaseList(d, state, load) {
    var frag = [];
    var fb = X.filterBar([
      { key: "case_status", label: "状态", type: "select",
        options: ["", "待审核", "审核中", "已通过", "已拒绝", "已关闭"].map(function (x) {
          return { value: x, label: x || "全部" }; }) },
      { key: "risk_level", label: "风险等级", type: "select",
        options: ["", "低", "中", "高", "极高"].map(function (x) {
          return { value: x, label: x || "全部" }; }) },
      { key: "user_id", label: "用户 ID", placeholder: "U0001" },
      { key: "keyword", label: "关键字", placeholder: "案件/事件源 ID" }
    ], function (vals) {
      state.filters = {}; Object.keys(vals).forEach(function (k) { state.filters[k] = vals[k]; });
      state.offset = 0; load();
    }, { extra: h("button.btn.btn-sm", { text: "只看活跃",
      onclick: function () { state.filters = { active_only: "true" }; state.offset = 0; load(); } }) });
    frag.push(fb.el);
    frag.push(h("div.mt14"));

    var summary = d.status_summary || {};
    var badges = Object.keys(summary).map(function (k) {
      return X.h("span.tag.tag-dot", { class: (X.CASE_TAG[k] || "gray") === "gray" ? "tag-gray" : "tag-" + (X.CASE_TAG[k] || "gray").replace("gray", "gray") },
        null, [ k + " " + summary[k] ]);
    });
    var card = X.card("案件工作台", null, {
      sub: "共 " + X.num(d.total, 0) + " 个", cls: "mb0 mt10",
      actions: badges.length ? h("div.row", { style: { gap: "6px", flexWrap: "wrap" } }, badges) : null
    });
    var body = card.querySelector(".card-body");
    body.appendChild(X.table(
      [ { key: "case_id", label: "案件 ID", width: "190px",
          render: function (r) { return h("span.chip", { text: r.case_id }); } },
        { key: "user_id", label: "用户", width: "84px" },
        { key: "event_type", label: "事件", width: "84px" },
        { key: "case_status", label: "状态", width: "84px", render: function (r) {
            return X.caseTag(r.case_status); } },
        { key: "risk_level", label: "等级", width: "70px", render: function (r) {
            return X.levelTag(r.risk_level); } },
        { key: "final_score", label: "融合分", align: "right", cls: "num", width: "76px",
          render: function (r) {
            return h("span" + (X.scoreClass(r.final_score).replace("c-", ".c-")),
              { text: X.num(r.final_score, 0) }); } },
        { key: "decision", label: "决策", width: "84px", render: function (r) {
            return X.decisionTag(r.decision); } },
        { key: "hit_rules", label: "命中", align: "right", cls: "num", width: "60px",
          render: function (r) { return X.num((r.hit_rules || []).length, 0); } },
        { key: "create_time", label: "创建", width: "140px",
          render: function (r) { return h("span.mut.f-12", { text: X.dt(r.create_time, "short") }); } } ],
      d.items || [], { onRowClick: function (r) { location.hash = "#/case?id=" + r.case_id; },
                        emptyText: "暂无案件（待审核/审核中）" }));
    body.appendChild(X.pager(d.total, state.limit, state.offset, function (off) {
      state.offset = off; load();
    }));
    frag.push(card);
    return frag;
  }

  function renderCaseDetail(view, id) {
    X.mount(view, X.loadingBlock("加载案件详情…"));
    X.api.get("/api/cases/" + encodeURIComponent(id)).then(function (d) {
      X.mount(view, buildCaseDetail(d.data, d.meta, id));
    }).catch(function (err) {
      X.mount(view, X.errorBlock(err, function () { renderCaseDetail(view, id); }));
    });
  }

  function buildCaseDetail(c, meta, id) {
    var frag = [];
    frag.push(h("div.row.mb14", null, [
      h("button.btn.btn-sm", { onclick: function () { location.hash = "#/case"; } },
        [ X.icon("chevR", 13), "返回列表" ]),
      h("span.spacer"),
      X.tag(id, "gray")
    ]));

    /* 基本信息 */
    var card = X.card("案件信息", null, { cls: "mb14" });
    var b = card.querySelector(".card-body");
    b.appendChild(X.kv([
      [ "当前状态", X.caseTag(c.case_status) ],
      [ "风险等级", X.levelTag(c.risk_level) ],
      [ "决策", X.decisionTag(c.decision) ],
      [ "融合分", h("b" + (X.scoreClass(c.final_score).replace("c-", ".c-")),
          { text: X.num(c.final_score, 1) }) ],
      [ "用户", c.user_id + (c.user_name ? "（" + c.user_name + "）" : "") ],
      [ "事件源", c.source_id ],
      [ "事件类型", c.event_type ],
      [ "审核人", c.reviewer || "—" ],
      [ "审核意见", c.review_comment || "—" ],
      [ "规则分 / 模型分", X.num(c.rule_score, 1) + " / " + X.num(c.ml_score, 1) ],
      [ "创建时间", X.dt(c.create_time) ],
      [ "关联评估", c.assessment_id || "—" ]
    ], { two: true }));
    b.appendChild(h("div.mt10.alert.alert-info", null, [
      X.icon("info", 16), h("div", null, [ h("b", { text: "决策依据" }), c.reason || "-" ]) ]));
    frag.push(card);

    /* 状态机 + 流转 */
    frag.push(buildFSM(c, meta));

    /* 命中规则 */
    frag.push(renderHitRules(c.hit_rules, "命中规则（" + (c.hit_rules || []).length + "）"));

    /* 特征快照 */
    if (c.feature_snapshot && typeof c.feature_snapshot === "object") {
      var fc = X.card("特征快照", null, { sub: "来自评估落库", cls: "mt14 mb0" });
      var fb = fc.querySelector(".card-body");
      var grid = h("div.feat-grid");
      Object.keys(c.feature_snapshot).forEach(function (k) {
        grid.appendChild(h("div.feat", null, [
          h("div.feat-head", null, [
            h("span.feat-name", { text: k, title: k }),
            X.tag("U", "blue")
          ]),
          h("div.feat-val", { text: X.num(c.feature_snapshot[k], 2) }),
          h("div.feat-label", { text: k })
        ]));
      });
      fb.appendChild(grid);
      frag.push(fc);
    }

    /* 操作轨迹（审计） */
    frag.push(buildActionLogs(c.action_logs, id));
    return frag;
  }

  function buildFSM(c, meta) {
    var sm = (meta && meta.state_machine) || { statuses: [], transitions: [] };
    var card = X.card("案件状态机（5 态 · 7 条合法边）", null, { cls: "mt14 mb0" });
    var body = card.querySelector(".card-body");
    var order = ["待审核", "审核中", "已通过", "已拒绝", "已关闭"];
    var statuses = sm.statuses && sm.statuses.length ? sm.statuses : order;
    var fsm = h("div.fsm");
    statuses.forEach(function (st, idx) {
      if (idx > 0) fsm.appendChild(h("span.fsm-arrow", null, X.icon("chevR", 14)));
      var cls = "fsm-node";
      if (st === c.case_status) cls += " is-current";
      else if (st === "已通过" || st === "已关闭") cls += " is-done";
      else if (st === "已拒绝") cls += " is-reject";
      fsm.appendChild(h("span." + cls, { text: st }));
    });
    body.appendChild(fsm);

    var allowed = c.allowed_transitions || [];
    if (allowed.length) {
      body.appendChild(h("div.mt14.sub.mut.f-12", { text: "可执行流转：" }));
      var trans = h("div.transitions.mt6");
      var descMap = { "审核中": "领取并进入审核", "已通过": "确认通过（回写标签 0）",
        "已拒绝": "确认拒绝（回写标签 1）", "已关闭": "关闭并归档" };
      allowed.forEach(function (to) {
        trans.appendChild(h("div.transition", { onclick: function () { openTransition(c, to); } }, [
          h("div", null, [
            h("div.tr-to", { text: "流转至 " + to }),
            h("div.tr-desc", { text: descMap[to] || "" })
          ]),
          h("span.tr-go", null, X.icon("arrowR", 15))
        ]));
      });
      body.appendChild(trans);
    } else {
      body.appendChild(h("div.mt14.mut.f-12", { text: "当前为终态，不可再流转。" }));
    }
    return card;
  }

  function openTransition(c, target) {
    var id = c.case_id;
    var operator = X.input({ placeholder: "审核人（必填）" });
    var comment = X.textarea({ placeholder: "审核意见（可选）", style: { minHeight: "60px" } });
    X.modal({
      title: "案件流转：" + c.case_status + " → " + target,
      width: "sm",
      content: [ X.field("操作人", operator, { required: true }),
                 X.field("审核意见", comment) ],
      actions: [
        { label: "取消", onClick: function () {} },
        { label: "确认流转", variant: "primary", onClick: function () {
            if (!operator.value.trim()) { X.toast.warn("请填写操作人"); return false; }
            X.api.put("/api/cases/" + encodeURIComponent(id) + "/status", {
              case_status: target, operator: operator.value.trim(),
              review_comment: comment.value.trim()
            }).then(function (r) {
              X.toast.ok("已流转至 " + target);
              renderCaseDetail(X.$("#view"), id);
            }).catch(function (err) { X.toast.err(err.message); return false; });
          } }
      ]
    });
  }

  function buildActionLogs(logs, id) {
    var card = X.card("操作轨迹", null, { cls: "mt14 mb0" });
    var body = card.querySelector(".card-body");
    if (!logs || !logs.length) {
      body.appendChild(X.emptyBlock("暂无操作记录"));
      return card;
    }
    body.appendChild(X.table(
      [ { key: "create_time", label: "时间", width: "140px",
          render: function (r) { return h("span.mut.f-12", { text: X.dt(r.create_time, "short") }); } },
        { key: "operator", label: "操作人", width: "90px" },
        { key: "action_type", label: "动作", width: "150px" },
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
      logs, { empty: false }));
    return card;
  }

  /* ================================================================ 规则引擎 */
  function rulePage(view) {
    var state = { limit: 30, offset: 0, filters: {} };
    function load() {
      X.mount(view, X.loadingBlock("加载规则列表…"));
      var qs = Object.assign({ limit: state.limit, offset: state.offset }, state.filters);
      X.api.get("/api/rules", qs).then(function (d) {
        X.mount(view, buildRuleList(d, state, load));
      }).catch(function (err) {
        X.mount(view, X.errorBlock(err, load));
      });
    }
    load();
  }

  function buildRuleList(d, state, load) {
    var frag = [];
    var meta = d.meta || {};
    var fb = X.filterBar([
      { key: "rule_category", label: "大类", type: "select",
        options: [""].concat((meta.categories || [])).map(function (x) {
          return { value: x, label: x || "全部" }; }) },
      { key: "event_type", label: "事件类型", type: "select",
        options: [""].concat(["考试", "作业", "选课", "成绩申诉"]).map(function (x) {
          return { value: x, label: x || "全部" }; }) },
      { key: "is_enabled", label: "状态", type: "select",
        options: [ { value: "", label: "全部" }, { value: "1", label: "启用" }, { value: "0", label: "停用" } ] },
      { key: "keyword", label: "关键字", placeholder: "规则 ID / 名称" }
    ], function (vals) {
      state.filters = {}; Object.keys(vals).forEach(function (k) { state.filters[k] = vals[k]; });
      state.offset = 0; load();
    }, { extra: h("button.btn.btn-sm.btn-primary", { text: "新增规则",
      onclick: function () { openRuleEditor(meta, null, load); } }) });
    frag.push(fb.el);
    frag.push(h("div.mt14"));

    var head = h("div.row.mb10", null, [
      X.tag("共 " + d.total + " 条规则", "gray"),
      X.tag("累计命中 " + X.num(d.total_hit_count, 0), "blue"),
      X.tag("算子 " + (meta.op_count || 14), "purple"),
      X.tag("特征 " + (meta.feature_count || 25), "cyan"),
      h("span.spacer"),
      h("button.btn.btn-sm", { text: "规则测试器", onclick: function () { openRuleTester(meta, null); } })
    ]);
    frag.push(head);

    var card = X.card(null, buildRuleTable(d.items || [], meta, load), { cls: "mb0" });
    frag.push(card);
    return frag;
  }

  function buildRuleTable(items, meta, reload) {
    return X.table(
      [ { key: "rule_id", label: "规则 ID", width: "92px" },
        { key: "rule_name", label: "名称", render: function (r) {
            return h("span", null, [ r.rule_name, " ", r.is_veto ? X.tag("否决", "red", "tag-dot") : null ]); } },
        { key: "rule_category", label: "大类", width: "110px" },
        { key: "event_type", label: "事件", width: "84px", render: function (r) {
            return r.event_type || h("span.mut2", { text: "通用" }); } },
        { key: "risk_level", label: "等级", width: "70px", render: function (r) {
            return X.levelTag(r.risk_level); } },
        { key: "risk_score", label: "分", align: "right", cls: "num", width: "56px",
          render: function (r) { return X.num(r.risk_score, 0); } },
        { key: "action", label: "动作", width: "80px" },
        { key: "is_enabled", label: "状态", width: "70px", render: function (r) {
            return r.is_enabled ? X.tag("启用", "green") : X.tag("停用", "gray"); } },
        { key: "hit_count", label: "命中", align: "right", cls: "num", width: "60px",
          render: function (r) { return X.num(r.hit_count, 0); } },
        { key: "ops", label: "操作", width: "130px", render: function (r) {
            return h("div.row", { style: { gap: "6px" } }, [
              h("button.btn.btn-sm", { text: "详情", onclick: function (e) {
                e.stopPropagation(); openRuleDetail(r, meta, reload); } }),
              h("button.btn.btn-sm", { text: "测试", onclick: function (e) {
                e.stopPropagation(); openRuleTester(meta, r); } })
            ]); } } ],
      items, { onRowClick: function (r) { openRuleDetail(r, meta, reload); },
                emptyText: "暂无规则" });
  }

  function condToText(cond) {
    if (!cond || typeof cond !== "object") return "—";
    if (cond.and) return "( " + cond.and.map(condToText).join(" AND ") + " )";
    if (cond.or) return "( " + cond.or.map(condToText).join(" OR ") + " )";
    if (cond.not) return "NOT " + condToText(cond.not);
    return (cond.field || "?") + " " + (cond.op || "?") + " " +
      (Array.isArray(cond.value) ? "[" + cond.value.join(",") + "]" : cond.value);
  }

  function openRuleDetail(r, meta, reload) {
    var body = [
      X.kv([
        [ "规则 ID", r.rule_id ],
        [ "名称", r.rule_name ],
        [ "大类", r.rule_category ],
        [ "事件类型", r.event_type || "通用" ],
        [ "风险等级", r.risk_level ],
        [ "风险分", X.num(r.risk_score, 0) ],
        [ "动作", r.action ],
        [ "优先级", X.num(r.priority, 0) ],
        [ "状态", r.is_enabled ? "启用" : "停用" ],
        [ "命中次数", X.num(r.hit_count, 0) ]
      ], { two: true }),
      h("div.mt12"),
      h("div.sub.mut.f-12.mb6", { text: "条件表达式" }),
      X.jsonBlock(r.rule_condition, true),
      r.description ? h("div.mt10.mut.f-12", { text: "说明：" + r.description }) : null
    ];
    X.modal({
      title: "规则详情 · " + r.rule_id,
      width: "lg",
      content: body,
      actions: [
        { label: "测试此规则", onClick: function () { openRuleTester(meta, r); } },
        { label: "编辑", variant: "primary", onClick: function () { openRuleEditor(meta, r, reload); } }
      ]
    });
  }

  function openRuleEditor(meta, r, reload) {
    var isEdit = !!r;
    var fId = X.input({ value: isEdit ? r.rule_id : "", disabled: isEdit });
    var fName = X.input({ value: isEdit ? r.rule_name : "" });
    var fCat = X.select((meta.categories || []).map(function (x) { return { value: x, label: x }; }),
      { value: isEdit ? r.rule_category : (meta.categories || [])[0] });
    var fEvent = X.select(["", "考试", "作业", "选课", "成绩申诉"].map(function (x) {
      return { value: x, label: x || "通用" }; }), { value: isEdit ? (r.event_type || "") : "" });
    var fLevel = X.select((meta.risk_levels || ["低", "中", "高", "极高"]).map(function (x) {
      return { value: x, label: x }; }), { value: isEdit ? r.risk_level : "中" });
    var fScore = X.input({ type: "number", value: isEdit ? r.risk_score : 0 });
    var fAction = X.select((meta.actions || ["通过", "标记", "人工审核", "拒绝"]).map(function (x) {
      return { value: x, label: x }; }), { value: isEdit ? r.action : "标记" });
    var fPriority = X.input({ type: "number", value: isEdit ? r.priority : 0 });
    var fEnabled = X.select([ { value: "1", label: "启用" }, { value: "0", label: "停用" } ],
      { value: isEdit ? String(r.is_enabled) : "1" });
    var fDesc = X.input({ value: isEdit ? (r.description || "") : "" });
    var fCond = X.textarea({ value: isEdit ? JSON.stringify(r.rule_condition, null, 2) :
      '{\n  "field": "order_total_amount",\n  "op": ">",\n  "value": 5000\n}' });

    X.modal({
      title: (isEdit ? "编辑规则 · " : "新增规则 · ") + (isEdit ? r.rule_id : ""),
      width: "lg",
      content: [
        h("div.form-row", null, [
          cell("规则 ID", fId), cell("名称", fName), cell("大类", fCat)
        ]),
        h("div.form-row", null, [
          cell("事件类型", fEvent), cell("风险等级", fLevel), cell("风险分", fScore)
        ]),
        h("div.form-row", null, [
          cell("动作", fAction), cell("优先级", fPriority), cell("状态", fEnabled)
        ]),
        X.field("说明", fDesc),
        X.field("条件表达式（JSON）", fCond, { tip: "支持 14 种 op：> >= < <= == != in not_in between not_between exists 以及 and / or / not 嵌套" })
      ],
      actions: [
        { label: "取消", onClick: function () {} },
        { label: isEdit ? "保存修改" : "创建规则", variant: "primary", onClick: function () {
            var body = {
              rule_name: fName.value.trim(), rule_category: fCat.value,
              event_type: fEvent.value, risk_level: fLevel.value,
              risk_score: Number(fScore.value || 0), action: fAction.value,
              priority: Number(fPriority.value || 0),
              is_enabled: fEnabled.value === "1", description: fDesc.value.trim(),
              rule_condition: fCond.value
            };
            if (!body.rule_name) { X.toast.warn("请填写规则名称"); return false; }
            var p;
            if (isEdit) p = X.api.put("/api/rules/" + encodeURIComponent(r.rule_id), body);
            else { body.rule_id = fId.value.trim();
              if (!body.rule_id) { X.toast.warn("请填写规则 ID"); return false; }
              p = X.api.post("/api/rules", body); }
            p.then(function () {
              X.toast.ok(isEdit ? "规则已更新" : "规则已创建");
              if (reload) reload();
            }).catch(function (err) { X.toast.err(err.message); return false; });
          } }
      ]
    });
  }

  function cell(label, ctrl) { return h("div.field", null, [ h("label.label", { text: label }), ctrl ]); }

  function openRuleTester(meta, preset) {
    var cond = X.textarea({ value: preset ? JSON.stringify(preset.rule_condition, null, 2) :
      '{\n  "and": [\n    {"field": "order_total_amount", "op": ">", "value": 5000},\n    {"field": "user_refund_rate", "op": ">=", "value": 0.5}\n  ]\n}' });
    var feats = X.textarea({ value: '{\n  "order_total_amount": 8000,\n  "user_refund_rate": 0.6\n}' });
    var resultBox = h("div#rule-test-result");

    X.modal({
      title: "规则测试器（14 算子逐节点求值）",
      width: "xl",
      content: [
        h("div.grid.g2", null, [
          h("div", null, [
            h("div.sub.mut.f-12.mb6", { text: "条件表达式（JSON）" }), cond,
            h("div.sub.mut.f-12.mt10.mb6", { text: "特征输入（JSON：{特征名: 数值}）" }), feats
          ]),
          h("div", null, [
            h("div.sub.mut.f-12.mb6", { text: "14 种算子参考" }),
            opGrid(meta)
          ])
        ]),
        h("div.mt12"),
        h("div.row", null, [
          h("button.btn.btn-primary.btn-sm", { text: "运行测试", onclick: run }),
          h("span.spacer"),
          h("span.mut.f-12", { id: "rule-test-hint" })
        ]),
        h("div.mt12", null, resultBox)
      ],
      actions: [ { label: "关闭", onClick: function () {} } ]
    });

    function run() {
      var condObj, featObj;
      try { condObj = JSON.parse(cond.value); } catch (e) { X.toast.warn("条件不是合法 JSON"); return; }
      try { featObj = JSON.parse(feats.value); } catch (e) { X.toast.warn("特征不是合法 JSON"); return; }
      X.mount(resultBox, X.loadingBlock("求值中…"));
      var payload = preset ? { rule_id: preset.rule_id, features: featObj } :
        { rule_condition: condObj, features: featObj };
      X.api.post("/api/rules/test", payload).then(function (d) {
        X.mount(resultBox, buildTrace(d));
      }).catch(function (err) { X.mount(resultBox, X.errorBlock(err)); });
    }
  }

  function opGrid(meta) {
    var ops = (meta && meta.ops) || [];
    return h("div.op-grid", null, ops.map(function (o) {
      return h("div.op" + (o.kind === "逻辑" ? ".t-logic" : ""), { title: o.example }, [
        h("div.op-sym", { text: o.op }),
        h("div.op-desc", { text: o.desc })
      ]);
    }));
  }

  function buildTrace(d) {
    var frag = [];
    if (!d.success) {
      frag.push(X.alert("danger", "条件非法", (d.errors || []).join("；")));
      return frag;
    }
    var verdict = d.hit
      ? X.alert("danger", "命中（Hit）", "该条件下规则触发")
      : X.alert("ok", "未命中（No Hit）", "该条件下规则不触发");
    frag.push(verdict);
    if (d.condition) {
      frag.push(h("div.sub.mut.f-12.mt10.mb6", { text: "解析后的条件" }));
      frag.push(X.jsonBlock(d.condition, true));
    }
    frag.push(h("div.sub.mut.f-12.mt10.mb6", { text: "求值轨迹（逐节点）" }));
    frag.push(renderTrace(d.trace || [], 0));
    return frag;
  }

  function renderTrace(trace, _depth) {
    var wrap = h("div.trace");
    (trace || []).forEach(function (node) {
      var isTrue = node.result === true;
      var children = h("div.trace-children");
      if (node.children && node.children.length) {
        children.appendChild(renderTrace(node.children, 0));
      }
      wrap.appendChild(h("div.trace-node" + (isTrue ? ".is-true" : ".is-false"), null, [
        h("span", { text: node.node }),
        h("span.tn-res", { text: isTrue ? "✓" : "✗" }),
        node.note ? h("span.mut2.f-11", { text: " · " + node.note }) : null
      ]));
    });
    return wrap;
  }

  /* ================================================================ 黑名单 */
  function blacklistPage(view) {
    var state = { limit: 50, offset: 0, filters: {} };
    function load() {
      X.mount(view, X.loadingBlock("加载黑名单…"));
      var qs = Object.assign({ limit: state.limit, offset: state.offset }, state.filters);
      X.api.get("/api/blacklist", qs).then(function (d) {
        X.mount(view, buildBlacklist(d, state, load));
      }).catch(function (err) {
        X.mount(view, X.errorBlock(err, load));
      });
    }
    load();
  }

  function buildBlacklist(d, state, load) {
    var frag = [];
    var meta = d.meta || {};
    var fb = X.filterBar([
      { key: "blacklist_type", label: "类型", type: "select",
        options: [""].concat(meta.types || []).map(function (x) { return { value: x, label: x || "全部" }; }) },
      { key: "keyword", label: "关键字", placeholder: "值 / 原因" }
    ], function (vals) {
      state.filters = {}; Object.keys(vals).forEach(function (k) { state.filters[k] = vals[k]; });
      state.offset = 0; load();
    }, { extra: h("button.btn.btn-sm.btn-primary", { text: "加入黑名单",
      onclick: function () { openBlacklistEditor(meta, load); } }) });
    frag.push(fb.el);
    frag.push(h("div.mt14"));

    frag.push(h("div.row.mb10", null, [
      X.tag("生效 " + X.num(d.total, 0), "red"),
      X.tag("累计命中 " + X.num(d.total_hit_count, 0), "orange"),
      (meta.type_stats ? Object.keys(meta.type_stats).map(function (t) {
        return X.tag(t + " " + d.type_stats[t], "gray"); }) : null)
    ]));

    var card = X.card(null, null, { cls: "mb0 mt10" });
    var body = card.querySelector(".card-body");
    body.appendChild(X.table(
      [ { key: "blacklist_id", label: "ID", width: "64px",
          render: function (r) { return "#" + r.blacklist_id; } },
        { key: "blacklist_type", label: "类型", width: "84px" },
        { key: "blacklist_value", label: "值", render: function (r) {
            return h("span.chip", { text: r.blacklist_value }); } },
        { key: "risk_level", label: "等级", width: "70px", render: function (r) {
            return X.levelTag(r.risk_level); } },
        { key: "reason", label: "原因" },
        { key: "hit_count", label: "命中", align: "right", cls: "num", width: "60px",
          render: function (r) { return X.num(r.hit_count, 0); } },
        { key: "status", label: "状态", width: "90px", render: function (r) {
            if (r.expired) return X.tag("已过期", "gray");
            if (!r.is_enabled) return X.tag("已停用", "gray");
            return X.tag("生效", "green"); } },
        { key: "expire_time", label: "过期", width: "150px",
          render: function (r) { return r.expire_time ? h("span.mut.f-12",
            { text: X.dt(r.expire_time, "short") }) : X.tag("永久", "gray"); } },
        { key: "ops", label: "操作", width: "80px", render: function (r) {
            return h("button.btn.btn-sm", { text: "解除", onclick: function (e) {
              e.stopPropagation(); removeBlacklist(r, load); } }); } } ],
      d.items || [], { onRowClick: function (r) { X.toast.ok("ID#" + r.blacklist_id + " · " +
          r.blacklist_type + " = " + r.blacklist_value); }, emptyText: "黑名单为空" }));
    frag.push(card);
    return frag;
  }

  function openBlacklistEditor(meta, reload) {
    var fType = X.select((meta.types || ["用户", "账号", "设备", "手机号", "IP"]).map(function (x) {
      return { value: x, label: x }; }), { value: (meta.types || [])[0] });
    var fValue = X.input({ placeholder: "如 U0001 / 8.8.8.8" });
    var fLevel = X.select((meta.risk_levels || ["低", "中", "高", "极高"]).map(function (x) {
      return { value: x, label: x }; }), { value: "高" });
    var fReason = X.input({ placeholder: "拉黑原因" });
    var fExpire = X.input({ placeholder: "留空=永久（YYYY-MM-DD HH:MM:SS）" });
    X.modal({
      title: "加入黑名单",
      width: "sm",
      content: [
        h("div.form-row", null, [ cell("类型", fType), cell("风险等级", fLevel) ]),
        X.field("值", fValue, { required: true }),
        X.field("原因", fReason),
        X.field("过期时间", fExpire, { tip: "留空表示永久拉黑；命中即触发一票否决（极高）" })
      ],
      actions: [
        { label: "取消", onClick: function () {} },
        { label: "确认拉黑", variant: "primary", onClick: function () {
            if (!fValue.value.trim()) { X.toast.warn("请填写值"); return false; }
            X.api.post("/api/blacklist", {
              blacklist_type: fType.value, blacklist_value: fValue.value.trim(),
              risk_level: fLevel.value, reason: fReason.value.trim() || "人工拉黑",
              expire_time: fExpire.value.trim(), source: "人工", operator: "admin"
            }).then(function () {
              X.toast.ok("已加入黑名单");
              if (reload) reload();
            }).catch(function (err) { X.toast.err(err.message); return false; });
          } }
      ]
    });
  }

  function removeBlacklist(r, reload) {
    X.confirmModal({
      title: "解除黑名单",
      message: "确认解除 " + r.blacklist_type + " = " + r.blacklist_value + " ？",
      okText: "确认解除", danger: true
    }).then(function (ok) {
      if (!ok) return;
      X.api.del("/api/blacklist/" + encodeURIComponent(r.blacklist_id) + "?operator=admin")
        .then(function () { X.toast.ok("已解除拉黑"); if (reload) reload(); })
        .catch(function (err) { X.toast.err(err.message); });
    });
  }

  /* 注册 */
  global.Pages = global.Pages || {};
  global.Pages["case"] = casePage;
  global.Pages["rule"] = rulePage;
  global.Pages["blacklist"] = blacklistPage;
})(window);
