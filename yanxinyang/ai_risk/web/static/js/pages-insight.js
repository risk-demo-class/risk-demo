/* ==========================================================================
   pages-insight.js —— 洞察组：用户画像 / 业务数据 / AI 助手
   ========================================================================== */
(function (global) {
  "use strict";
  var X = global.X, C = global.C, h = X.h;

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

  var DECISION_COLOR = { "通过": "#16a34a", "标记": "#0891b2", "人工审核": "#d97706", "拒绝": "#dc2626" };

  /* ================================================================ 用户画像 */
  function profilePage(view) {
    var q = parseQuery(location.hash);
    if (q.user_id) { renderProfileDetail(view, q.user_id); return; }
    renderProfileList(view);
  }

  function renderProfileList(view) {
    var state = { limit: 20, offset: 0, filters: {} };
    function load() {
      X.mount(view, X.loadingBlock("加载用户画像…"));
      var qs = Object.assign({ limit: state.limit, offset: state.offset }, state.filters);
      X.api.get("/api/profiles", qs).then(function (d) {
        X.mount(view, buildProfileList(d, state, load));
      }).catch(function (err) {
        X.mount(view, X.errorBlock(err, load));
      });
    }
    load();
  }

  function buildProfileList(d, state, load) {
    var frag = [];
    var fb = X.filterBar([
      { key: "keyword", label: "用户 / 昵称", placeholder: "U0001 / 张三" },
      { key: "profile_level", label: "画像等级", type: "select",
        options: ["", "低", "中", "高", "极高"].map(function (x) { return { value: x, label: x || "全部" }; }) },
      { key: "min_score", label: "最低分", placeholder: "如 60" }
    ], function (vals) {
      state.filters = {}; Object.keys(vals).forEach(function (k) { state.filters[k] = vals[k]; });
      state.offset = 0; load();
    });
    frag.push(fb.el);
    frag.push(h("div.mt14"));
    var card = X.card("用户风险画像", null, {
      sub: "共 " + X.num(d.total, 0) + " 个 · 按最高融合分倒排", cls: "mb0 mt10" });
    var body = card.querySelector(".card-body");
    body.appendChild(X.table(
      [ { key: "user_id", label: "用户", width: "84px" },
        { key: "user_name", label: "昵称" },
        { key: "profile_level", label: "画像等级", width: "84px", render: function (r) {
            return X.levelTag(r.profile_level); } },
        { key: "total_events", label: "事件", align: "right", cls: "num", width: "70px",
          render: function (r) { return X.num(r.total_events, 0); } },
        { key: "risk_event_count", label: "高危", align: "right", cls: "num", width: "70px",
          render: function (r) { return X.num(r.risk_event_count, 0); } },
        { key: "max_final_score", label: "最高分", align: "right", cls: "num", width: "76px",
          render: function (r) {
            return h("span" + (X.scoreClass(r.max_final_score).replace("c-", ".c-")),
              { text: X.num(r.max_final_score, 0) }); } },
        { key: "avg_final_score", label: "均分", align: "right", cls: "num", width: "76px",
          render: function (r) { return X.num(r.avg_final_score, 1); } },
        { key: "last_decision", label: "最近决策", width: "84px", render: function (r) {
            return r.last_decision ? X.decisionTag(r.last_decision) : h("span.mut2", { text: "-" }); } } ],
      d.items || [], { onRowClick: function (r) { location.hash = "#/profile?user_id=" + r.user_id; },
                        emptyText: "暂无画像数据" }));
    body.appendChild(X.pager(d.total, state.limit, state.offset, function (off) {
      state.offset = off; load();
    }));
    frag.push(card);
    return frag;
  }

  function renderProfileDetail(view, user_id) {
    X.mount(view, X.loadingBlock("加载用户画像…"));
    X.api.get("/api/profiles/" + encodeURIComponent(user_id)).then(function (d) {
      X.mount(view, buildProfileDetail(d.data, user_id));
    }).catch(function (err) {
      X.mount(view, X.errorBlock(err, function () { renderProfileDetail(view, user_id); }));
    });
  }

  function buildProfileDetail(d, user_id) {
    var frag = [];
    var user = d.user || {};
    var p = d.profile || {};
    frag.push(h("div.row.mb14", null, [
      h("button.btn.btn-sm", { onclick: function () { location.hash = "#/profile"; } },
        [ X.icon("chevR", 13), "返回列表" ]),
      h("span.spacer"),
      X.tag(user_id, "gray"),
      user.user_name ? X.tag(user.user_name, "blue") : null,
      p.profile_level ? X.levelTag(p.profile_level) : null
    ]));

    /* 风险档案 */
    var card = X.card("风险档案", null, { cls: "mb14" });
    var b = card.querySelector(".card-body");
    b.appendChild(X.kv([
      [ "累计事件", X.num(p.total_events, 0) ],
      [ "高危事件", X.num(p.risk_event_count, 0) ],
      [ "通过 / 标记", X.num(p.pass_count, 0) + " / " + X.num(p.mark_count, 0) ],
      [ "人工审核 / 拒绝", X.num(p.review_count, 0) + " / " + X.num(p.reject_count, 0) ],
      [ "关联案件", X.num(p.case_count, 0) ],
      [ "撞黑次数", X.num(p.blacklist_hit_count, 0) ],
      [ "最高融合分", h("b" + (X.scoreClass(p.max_final_score).replace("c-", ".c-")),
          { text: X.num(p.max_final_score, 1) }) ],
      [ "平均融合分", X.num(p.avg_final_score, 1) ],
      [ "最近决策", p.last_decision ? X.decisionTag(p.last_decision) : "—" ],
      [ "最近事件", X.dt(p.last_event_time) ]
    ], { two: true }));
    frag.push(card);

    /* 业务总览 + 决策分布 */
    frag.push(h("div.grid.g2.mb14", null, [
      businessCard(d.business),
      decisionCard(d.decision_histogram)
    ]));

    /* 事件时间线 */
    frag.push(eventsCard(d.events));

    /* 案件 + 地址 */
    frag.push(h("div.grid.g2.mb14", null, [
      casesCard(d.cases),
      addressesCard(d.addresses)
    ]));

    /* 黑名单命中 */
    if (d.blacklist && d.blacklist.length) {
      var bc = X.card("黑名单命中", null, { cls: "mb0" });
      var bb = bc.querySelector(".card-body");
      bb.appendChild(X.table(
        [ { key: "blacklist_type", label: "类型", width: "84px" },
          { key: "blacklist_value", label: "值" },
          { key: "risk_level", label: "等级", width: "70px", render: function (r) {
              return X.levelTag(r.risk_level); } },
          { key: "reason", label: "原因" } ],
        d.blacklist, { empty: false }));
      frag.push(bc);
    }
    return frag;
  }

  function businessCard(biz) {
    var card = X.card("业务总览", null, { cls: "mb0" });
    var body = card.querySelector(".card-body");
    var grid = h("div.metric-grid");
    var items = [
      ["学习行为数", biz.order_count], ["学习投入额", biz.order_amount, true],
      ["申诉", biz.refund_count], ["退课", biz.postsale_count],
      ["反馈", biz.complaint_count], ["取消选课", biz.cancel_count],
      ["关联实体", biz.address_count], ["设备", biz.device_count], ["登录", biz.login_count]
    ];
    items.forEach(function (it) {
      grid.appendChild(h("div.metric", null, [
        h("div.metric-name", { text: it[0] }),
        h("div.metric-val", { text: it[2] ? X.money(it[1], 0) : X.num(it[1], 0) })
      ]));
    });
    body.appendChild(grid);
    return card;
  }

  function decisionCard(hist) {
    var card = X.card("决策分布", null, { cls: "mb0" });
    var body = card.querySelector(".card-body");
    var items = Object.keys(hist || {}).map(function (k) {
      return { label: k, value: hist[k], color: DECISION_COLOR[k] || "#94a3b8" };
    });
    body.appendChild(items.length ? C.donut(items) : X.emptyBlock("暂无决策数据"));
    return card;
  }

  function eventsCard(events) {
    var card = X.card("风控事件时间线", null, { sub: "最近 50 条", cls: "mb0 mt14" });
    var body = card.querySelector(".card-body");
    body.appendChild(X.table(
      [ { key: "event_time", label: "时间", width: "140px",
          render: function (r) { return h("span.mut.f-12", { text: X.dt(r.event_time, "short") }); } },
        { key: "event_type", label: "事件", width: "84px" },
        { key: "source_id", label: "事件源", render: function (r) {
            return h("span.chip", { text: r.source_id }); } },
        { key: "final_score", label: "融合分", align: "right", cls: "num", width: "76px",
          render: function (r) {
            return h("span" + (X.scoreClass(r.final_score).replace("c-", ".c-")),
              { text: X.num(r.final_score, 0) }); } },
        { key: "decision", label: "决策", width: "84px", render: function (r) {
            return X.decisionTag(r.decision); } },
        { key: "is_veto", label: "否决", width: "56px", align: "center",
          render: function (r) {
            return r.is_veto ? X.tag("否决", "red", "tag-dot") : h("span.mut2", { text: "-" }); } },
        { key: "reason", label: "依据", render: function (r) {
            return h("span.mut.f-12", { text: X.trunc(r.reason || "", 40) }); } } ],
      events || [], { emptyText: "暂无事件" }));
    return card;
  }

  function casesCard(cases) {
    var card = X.card("关联案件", null, { cls: "mb0" });
    var body = card.querySelector(".card-body");
    if (!cases || !cases.length) { body.appendChild(X.emptyBlock("无关联案件")); return card; }
    body.appendChild(X.table(
      [ { key: "case_id", label: "案件", width: "150px",
          render: function (r) { return h("span.chip", { text: r.case_id }); } },
        { key: "case_status", label: "状态", width: "84px", render: function (r) {
            return X.caseTag(r.case_status); } },
        { key: "risk_level", label: "等级", width: "70px", render: function (r) {
            return X.levelTag(r.risk_level); } },
        { key: "final_score", label: "分", align: "right", cls: "num", width: "60px",
          render: function (r) { return X.num(r.final_score, 0); } } ],
      cases, { empty: false }));
    return card;
  }

  function addressesCard(addrs) {
    var card = X.card("关联账号/设备", null, { cls: "mb0" });
    var body = card.querySelector(".card-body");
    if (!addrs || !addrs.length) { body.appendChild(X.emptyBlock("无关联实体")); return card; }
    body.appendChild(X.table(
      [ { key: "address_id", label: "ID", width: "120px" },
        { key: "receiver_name", label: "名称" },
        { key: "phone", label: "联系方式" },
        { key: "detail", label: "详情", render: function (r) {
            return h("span.mut.f-12", { text: X.trunc(r.detail || r.address_detail || "", 30) }); } },
        { key: "is_default", label: "默认", width: "60px", align: "center",
          render: function (r) { return r.is_default ? X.tag("默认", "green") : h("span.mut2", { text: "-" }); } } ],
      addrs, { empty: false }));
    return card;
  }

  /* ================================================================ 业务数据 */
  function businessPage(view) {
    var state = { table: null, offset: 0, limit: 20, filters: {}, columns: [] };
    var layout = h("div.grid", { style: { gridTemplateColumns: "240px 1fr", gap: "14px" } });
    var nav = h("div.dict-nav");
    var panel = h("div");
    layout.appendChild(nav);
    layout.appendChild(panel);
    X.mount(view, layout);

    X.api.get("/api/business/dictionary").then(function (d) {
      var groups = {};
      (d.tables || []).forEach(function (t) { (groups[t.group] = groups[t.group] || []).push(t); });
      X.$$(".dict-nav").length;
      X.mount(nav, Object.keys(groups).map(function (g) {
        return h("div", null, [
          h("div.dict-group", { text: g }),
          h("div", null, groups[g].map(function (t) {
            return h("div.dict-item", { "data-table": t.table, onclick: function () {
              X.$$(".dict-item", nav).forEach(function (x) { x.classList.remove("active"); });
              this.classList.add("active");
              selectTable(t);
            } }, [
              h("span.dt-name", { text: t.table }),
              h("span.dt-cn", { text: t.comment || "" })
            ]);
          }))
        ]);
      }));

      function selectTable(t) {
        state.table = t.table;
        state.offset = 0;
        state.filters = {};
        state.columns = t.columns || [];
        renderTablePanel(panel, state, t, function () { selectTable(t); });
      }

      // 默认选中第一张表
      var first = (d.tables || [])[0];
      if (first) {
        var el = X.$('.dict-item[data-table="' + first.table + '"]', nav);
        if (el) el.classList.add("active");
        selectTable(first);
      }
    }).catch(function (err) {
      X.mount(panel, X.errorBlock(err));
    });
  }

  function renderTablePanel(panel, state, tableMeta, reload) {
    X.mount(panel, X.loadingBlock("加载表数据…"));
    var qs = Object.assign({ limit: state.limit, offset: state.offset,
      order_by: state.filters.order_by || (state.columns[0] && state.columns[0].name),
      order: state.filters.order || "desc" }, state.filters);
    delete qs.order_by_dummy;
    X.api.get("/api/business/table/" + encodeURIComponent(state.table), qs).then(function (d) {
      X.mount(panel, buildTableBrowser(d, state, tableMeta, reload));
    }).catch(function (err) {
      X.mount(panel, X.errorBlock(err, reload));
    });
  }

  function buildTableBrowser(d, state, tableMeta, reload) {
    var frag = [];
    var cols = d.columns || state.columns;
    var fb = X.filterBar([
      { key: "keyword", label: "关键字", placeholder: "模糊搜索文本列" },
      { key: "user_id", label: "用户 ID", placeholder: "1001" },
      { key: "order_id", label: "学习记录 ID", placeholder: "ORD..." },
      { key: "order_by", label: "排序字段", type: "select",
        options: cols.map(function (c) { return { value: c.name, label: c.name }; }),
        width: "140px" }
    ], function (vals) {
      state.filters = vals; if (!vals.order_by) delete state.filters.order_by;
      state.offset = 0; reload();
    }, { extra: h("button.btn.btn-sm", { text: "切换排序",
      onclick: function () { state.filters.order = state.filters.order === "asc" ? "desc" : "asc";
        reload(); } }) });
    frag.push(fb.el);
    frag.push(h("div.mt14"));

    var card = X.card(tableMeta.table, null, {
      sub: (tableMeta.comment || "") + " · 共 " + X.num(d.total, 0) + " 行 · " + d.group,
      cls: "mb0 mt10" });
    var body = card.querySelector(".card-body");
    var columns = cols.map(function (c) {
      return { key: c.name, label: c.name,
        render: function (row) {
          var v = row[c.name];
          if (v === null || v === undefined || v === "") return h("span.mut2", { text: "-" });
          if (typeof v === "object") return h("span.chip", { text: JSON.stringify(v) });
          return String(v);
        } };
    });
    body.appendChild(X.table(columns, d.items || [], { emptyText: "该表暂无数据", compact: true }));
    body.appendChild(X.pager(d.total, state.limit, state.offset, function (off) {
      state.offset = off; reload();
    }));
    frag.push(card);
    return frag;
  }

  /* ================================================================ AI 助手 */
  function assistantPage(view) {
    var sessionId = "web-" + Date.now();
    var abort = null;

    var wrap = h("div.chat");
    var body = h("div.chat-body");
    var foot = h("div.chat-foot");

    var input = X.textarea({ placeholder: "输入问题，例如：给用户 1001 的考试记录 ORD10010001 做一次考试风控检查",
      style: { minHeight: "40px" } });
    var sendBtn = h("button.btn.btn-primary", { onclick: send }, [ X.icon("send", 14), "发送" ]);
    var stopBtn = h("button.btn.btn-danger", { style: { display: "none" }, onclick: function () {
      if (abort) { try { abort(); } catch (e) {} abort = null; }
      sendBtn.disabled = false;
      stopBtn.style.display = "none";
      sendBtn.style.display = "";
    } }, [ "⏹ 停止" ]);

    foot.appendChild(h("div.chat-input-row", null, [ input, sendBtn, stopBtn ]));
    wrap.appendChild(body);
    wrap.appendChild(foot);
    X.mount(view, wrap);

    function addMsg(role, text) {
      var el = h("div.msg" + (role === "user" ? ".is-user" : ""), null, [
        h("div.msg-avatar", { text: role === "user" ? "我" : "AI" }),
        h("div.msg-bubble", null, text != null ? [ document.createTextNode(text) ] : [])
      ]);
      body.appendChild(el);
      body.scrollTop = body.scrollHeight;
      return el;
    }
    function addToolBlock(name, args) {
      var el = h("div.msg", null, [
        h("div.msg-avatar", { text: "AI" }),
        h("div.msg-bubble", null, [
          h("div.msg-tool", null, [
            h("b", { text: "⚙ " + name }),
            h("div", { text: "参数：" + JSON.stringify(args || {}) })
          ])
        ])
      ]);
      body.appendChild(el);
      body.scrollTop = body.scrollHeight;
      return el;
    }
    function addThinking(text) {
      var el = h("div.msg", null, [
        h("div.msg-avatar", { text: "AI" }),
        h("div.msg-bubble", null, [ h("span.mut.f-12", { text: "💡 " + text }) ])
      ]);
      body.appendChild(el);
      body.scrollTop = body.scrollHeight;
      return el;
    }

    function send() {
      var msg = input.value.trim();
      if (!msg) return;
      input.value = "";
      addMsg("user", msg);
      var ai = addMsg("assistant", "");
      var textPara = ai.querySelector(".msg-bubble");
      var cursor = h("span.cursor");
      textPara.appendChild(cursor);
      sendBtn.disabled = true;
      sendBtn.style.display = "none";
      stopBtn.style.display = "";

      var toolBlock = null;
      abort = X.api.stream("/api/agent/chat", {
        message: msg, session_id: sessionId, operator: "运营", stream: true
      }, {
        event: function (evt, payload) {
          if (evt === "thinking") {
            addThinking(payload.text);
          } else if (evt === "tool_call") {
            toolBlock = addToolBlock(payload.name, payload.args);
          } else if (evt === "tool_result") {
            if (toolBlock) {
              var ok = payload.success;
              var r = payload.result;
              var txt = ok
                ? (typeof r === "object" ? X.trunc(JSON.stringify(r), 220) : String(r))
                : ("失败：" + (r && r.error ? r.error : ""));
              toolBlock.querySelector(".msg-tool").appendChild(
                h("div.mt6", { text: (ok ? "✓ " : "✗ ") + txt }));
            }
          } else if (evt === "delta") {
            if (cursor.parentNode) cursor.parentNode.removeChild(cursor);
            textPara.appendChild(document.createTextNode(payload.text));
            textPara.appendChild(cursor);
            body.scrollTop = body.scrollHeight;
          } else if (evt === "done") {
            if (cursor.parentNode) cursor.parentNode.removeChild(cursor);
            sendBtn.disabled = false;
            sendBtn.style.display = "";
            stopBtn.style.display = "none";
          } else if (evt === "error") {
            if (cursor.parentNode) cursor.parentNode.removeChild(cursor);
            textPara.appendChild(h("span.c-danger", { text: "⚠ " + (payload.message || "出错") }));
            sendBtn.disabled = false;
            sendBtn.style.display = "";
            stopBtn.style.display = "none";
          }
        },
        done: function () {
          if (cursor.parentNode) cursor.parentNode.removeChild(cursor);
          sendBtn.disabled = false;
          sendBtn.style.display = "";
          stopBtn.style.display = "none";
          abort = null;
        },
        error: function (err) {
          if (cursor.parentNode) cursor.parentNode.removeChild(cursor);
          textPara.appendChild(h("span.c-danger", { text: "⚠ " + (err.message || err) }));
          sendBtn.disabled = false;
          sendBtn.style.display = "";
          stopBtn.style.display = "none";
          abort = null;
        }
      });
    }

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
    });

    // 加载工具清单 + 示例
    X.api.get("/api/agent/tools").then(function (d) {
      addMsg("assistant", "你好，我是智学安·教育风控助手。我可以调用 8 个工具帮你做风险检查、查案件、看画像、"
        + "管黑名单、分析趋势与规则效果。直接说需求即可（下方示例可点击）。");
      var tips = h("div.chat-tips");
      (d.examples || []).forEach(function (ex) {
        tips.appendChild(h("span.chat-tip", { text: ex, onclick: function () {
          input.value = ex; send(); } }));
      });
      foot.insertBefore(tips, foot.firstChild);
    }).catch(function () { /* 不阻塞聊天 */ });

    // 返回清理函数：切换页面时中止 SSE
    return function () { if (abort) { try { abort(); } catch (e) {} abort = null; } };
  }

  /* 注册 */
  global.Pages = global.Pages || {};
  global.Pages["profile"] = profilePage;
  global.Pages["business"] = businessPage;
  global.Pages["assistant"] = assistantPage;
})(window);
