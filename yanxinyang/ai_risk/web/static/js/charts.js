/* ==========================================================================
   charts.js —— 纯 SVG 图表（零依赖，不引 Chart.js/ECharts）
   支持：折线（多系列）/ 柱状 / 水平条 / 环形 / 迷你趋势
   全部自适应宽度：用 viewBox + preserveAspectRatio，父容器宽度变了不用重绘。
   ========================================================================== */
(function (global) {
  "use strict";
  var X = global.X;
  var NS = "http://www.w3.org/2000/svg";

  /* 调色板：与 base.css 的语义色保持一致 */
  var PALETTE = ["#2563eb", "#dc2626", "#d97706", "#16a34a", "#0891b2", "#7c3aed",
                 "#db2777", "#0d9488"];

  function el(name, attrs, children) {
    var node = document.createElementNS(NS, name);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        node.setAttribute(k, v);
      });
    }
    if (children) {
      (Array.isArray(children) ? children : [children]).forEach(function (c) {
        if (c === null || c === undefined || c === false) return;
        node.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
      });
    }
    return node;
  }

  function svgRoot(w, h) {
    return el("svg", {
      viewBox: "0 0 " + w + " " + h,
      preserveAspectRatio: "xMidYMid meet",
      role: "img"
    });
  }

  /** 坐标轴刻度取整：让 max 落在 1/2/5×10^n 的整数倍上 */
  function niceMax(value, ticks) {
    if (!isFinite(value) || value <= 0) return ticks || 4;
    var rough = value / (ticks || 4);
    var mag = Math.pow(10, Math.floor(Math.log(rough) / Math.LN10));
    var norm = rough / mag;
    var step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
    return step * mag * (ticks || 4);
  }

  function fmtTick(v) {
    var n = Number(v);
    if (!isFinite(n)) return "0";
    if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(1).replace(/\.0$/, "") + "亿";
    if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(1).replace(/\.0$/, "") + "万";
    if (Number.isInteger(n)) return String(n);
    return n.toFixed(1);
  }

  /* ---------------------------------------------------------------- Tooltip */
  function attachTip(box) {
    var tip = X.h("div.chart-tip");
    box.appendChild(tip);
    return {
      show: function (html, x, y) {
        tip.innerHTML = html;
        tip.classList.add("show");
        var bw = box.clientWidth || 1;
        // 靠右时向左翻转，避免溢出容器
        var left = (x / bw) * 100;
        tip.style.left = left + "%";
        tip.style.top = y + "px";
        tip.style.transform = left > 68 ? "translate(-100%, -120%)" : "translate(-12px, -120%)";
      },
      hide: function () { tip.classList.remove("show"); }
    };
  }

  function legend(items) {
    return X.h("div.chart-legend", null, items.map(function (it) {
      return X.h("span", null, [
        X.h("i", { style: { background: it.color } }),
        it.label + (it.value !== undefined ? " " + it.value : "")
      ]);
    }));
  }

  function emptyChart(text) {
    return X.h("div.chart-empty", null, [X.icon("inbox", 26), text || "暂无数据"]);
  }

  /* ================================================================ 折线图 */
  /**
   * lineChart(labels, series, opts)
   *   series: [{name, data:[], color?, area?, dash?}]
   */
  function lineChart(labels, series, opts) {
    opts = opts || {};
    labels = labels || [];
    series = (series || []).filter(function (s) { return s && s.data; });
    if (!labels.length || !series.length) return emptyChart(opts.emptyText);

    var W = 720, H = opts.height || 260;
    var pad = { t: 16, r: 16, b: 30, l: 46 };
    var iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;

    var maxVal = 0;
    series.forEach(function (s) {
      s.data.forEach(function (v) { maxVal = Math.max(maxVal, Number(v) || 0); });
    });
    var top = opts.max || niceMax(maxVal, 4) || 4;
    var ticks = 4;

    var box = X.h("div.chart-box");
    var svg = svgRoot(W, H);
    var g = el("g");

    // 网格 + Y 轴刻度
    for (var i = 0; i <= ticks; i++) {
      var y = pad.t + ih - (ih * i / ticks);
      g.appendChild(el("line", {
        x1: pad.l, y1: y, x2: pad.l + iw, y2: y,
        stroke: i === 0 ? "#cbd5e1" : "#e9eef5", "stroke-width": 1
      }));
      g.appendChild(el("text", {
        x: pad.l - 8, y: y + 3.5, "text-anchor": "end",
        fill: "#94a3b8", "font-size": 10.5
      }, fmtTick(top * i / ticks)));
    }

    var stepX = labels.length > 1 ? iw / (labels.length - 1) : 0;
    var px = function (idx) { return pad.l + (labels.length > 1 ? idx * stepX : iw / 2); };
    var py = function (v) { return pad.t + ih - (Math.max(Number(v) || 0, 0) / top) * ih; };

    // X 轴标签（点多了就抽稀）
    var stride = Math.ceil(labels.length / 9);
    labels.forEach(function (lb, idx) {
      if (idx % stride !== 0 && idx !== labels.length - 1) return;
      g.appendChild(el("text", {
        x: px(idx), y: H - 9, "text-anchor": "middle", fill: "#94a3b8", "font-size": 10.5
      }, opts.formatLabel ? opts.formatLabel(lb) : lb));
    });

    series.forEach(function (s, si) {
      var color = s.color || PALETTE[si % PALETTE.length];
      var pts = s.data.map(function (v, idx) { return px(idx) + "," + py(v); });
      if (s.area !== false && series.length <= 2) {
        g.appendChild(el("polygon", {
          points: pad.l + "," + (pad.t + ih) + " " + pts.join(" ") + " " +
                  px(s.data.length - 1) + "," + (pad.t + ih),
          fill: color, opacity: 0.08
        }));
      }
      g.appendChild(el("polyline", {
        points: pts.join(" "), fill: "none", stroke: color,
        "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
        "stroke-dasharray": s.dash || null
      }));
      s.data.forEach(function (v, idx) {
        g.appendChild(el("circle", {
          cx: px(idx), cy: py(v), r: labels.length > 24 ? 2 : 3,
          fill: "#fff", stroke: color, "stroke-width": 1.8
        }));
      });
    });

    svg.appendChild(g);
    box.appendChild(svg);
    var tip = attachTip(box);

    // hover：找最近的 x 下标
    var hoverLine = el("line", {
      y1: pad.t, y2: pad.t + ih, stroke: "#94a3b8", "stroke-width": 1,
      "stroke-dasharray": "3 3", opacity: 0
    });
    g.appendChild(hoverLine);
    svg.addEventListener("mousemove", function (e) {
      var rect = svg.getBoundingClientRect();
      var ratio = W / rect.width;
      var mx = (e.clientX - rect.left) * ratio;
      var idx = labels.length > 1
        ? Math.round((mx - pad.l) / stepX)
        : 0;
      idx = Math.max(0, Math.min(labels.length - 1, idx));
      hoverLine.setAttribute("x1", px(idx));
      hoverLine.setAttribute("x2", px(idx));
      hoverLine.setAttribute("opacity", 1);
      var rows = series.map(function (s, si) {
        var color = s.color || PALETTE[si % PALETTE.length];
        return '<span style="color:' + color + '">●</span> ' + X.esc(s.name) + " <b>" +
               (opts.formatValue ? opts.formatValue(s.data[idx]) : X.num(s.data[idx])) + "</b>";
      });
      tip.show(X.esc(labels[idx]) + "<br>" + rows.join("<br>"),
               (px(idx) / W) * (rect.width), pad.t + 10);
    });
    svg.addEventListener("mouseleave", function () {
      hoverLine.setAttribute("opacity", 0);
      tip.hide();
    });

    var wrap = X.h("div", null, [box]);
    if (opts.legend !== false && series.length > 1) {
      wrap.appendChild(legend(series.map(function (s, si) {
        return { label: s.name, color: s.color || PALETTE[si % PALETTE.length] };
      })));
    }
    return wrap;
  }

  /* ================================================================ 柱状图 */
  function barChart(labels, values, opts) {
    opts = opts || {};
    labels = labels || [];
    values = values || [];
    if (!labels.length) return emptyChart(opts.emptyText);

    var W = 720, H = opts.height || 240;
    var pad = { t: 16, r: 16, b: 34, l: 46 };
    var iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
    var maxVal = Math.max.apply(null, values.map(Number).concat([0]));
    var top = opts.max || niceMax(maxVal, 4) || 4;

    var box = X.h("div.chart-box");
    var svg = svgRoot(W, H);
    var g = el("g");

    for (var i = 0; i <= 4; i++) {
      var y = pad.t + ih - (ih * i / 4);
      g.appendChild(el("line", {
        x1: pad.l, y1: y, x2: pad.l + iw, y2: y,
        stroke: i === 0 ? "#cbd5e1" : "#e9eef5"
      }));
      g.appendChild(el("text", {
        x: pad.l - 8, y: y + 3.5, "text-anchor": "end", fill: "#94a3b8", "font-size": 10.5
      }, fmtTick(top * i / 4)));
    }

    var slot = iw / labels.length;
    var bw = Math.min(slot * 0.6, 44);
    var tip = attachTip(box);

    labels.forEach(function (lb, idx) {
      var v = Number(values[idx]) || 0;
      var bh = (v / top) * ih;
      var cx = pad.l + slot * idx + slot / 2;
      var color = (opts.colors && opts.colors[idx]) || opts.color || PALETTE[0];
      var rect = el("rect", {
        x: cx - bw / 2, y: pad.t + ih - bh, width: bw, height: Math.max(bh, v > 0 ? 1.5 : 0),
        rx: 3, fill: color, opacity: 0.88, style: "cursor:pointer"
      });
      rect.addEventListener("mouseenter", function () {
        rect.setAttribute("opacity", 1);
        var rb = svg.getBoundingClientRect();
        tip.show("<b>" + X.esc(lb) + "</b><br>" +
                 (opts.formatValue ? opts.formatValue(v) : X.num(v)),
                 (cx / W) * rb.width, pad.t + ih - bh);
      });
      rect.addEventListener("mouseleave", function () {
        rect.setAttribute("opacity", 0.88);
        tip.hide();
      });
      g.appendChild(rect);
      if (opts.showValue !== false && labels.length <= 14) {
        g.appendChild(el("text", {
          x: cx, y: pad.t + ih - bh - 5, "text-anchor": "middle",
          fill: "#475569", "font-size": 10.5, "font-weight": 600
        }, fmtTick(v)));
      }
      g.appendChild(el("text", {
        x: cx, y: H - 11, "text-anchor": "middle", fill: "#64748b", "font-size": 10.5
      }, X.trunc(lb, labels.length > 8 ? 5 : 9)));
    });

    svg.appendChild(g);
    box.appendChild(svg);
    return box;
  }

  /* ================================================================ 水平条 */
  /** items: [{label, value, color?, note?}] —— 排行榜首选，标签长也不挤 */
  function hbarChart(items, opts) {
    opts = opts || {};
    items = items || [];
    if (!items.length) return emptyChart(opts.emptyText);

    var maxVal = Math.max.apply(null, items.map(function (i) { return Number(i.value) || 0; })
                                     .concat([0])) || 1;
    var wrap = X.h("div", null, items.map(function (it, idx) {
      var ratio = (Number(it.value) || 0) / maxVal;
      var color = it.color || opts.color || PALETTE[idx % PALETTE.length];
      return X.h("div.imp-row", null, [
        X.h("div.imp-name", { text: it.label, title: it.label }),
        X.h("div.imp-bar", null,
          X.h("div.bar.h8", null,
            X.h("i", { style: { width: (ratio * 100).toFixed(2) + "%", background: color } }))),
        X.h("div.imp-val", {
          text: opts.formatValue ? opts.formatValue(it.value) : X.num(it.value)
        })
      ]);
    }));
    return wrap;
  }

  /* ================================================================ 环形图 */
  /** items: [{label, value, color?}] */
  function donutChart(items, opts) {
    opts = opts || {};
    items = (items || []).filter(function (i) { return (Number(i.value) || 0) > 0; });
    if (!items.length) return emptyChart(opts.emptyText);

    var size = opts.size || 190;
    var thickness = opts.thickness || 26;
    var r = (size - thickness) / 2;
    var cx = size / 2, cy = size / 2;
    var total = items.reduce(function (s, i) { return s + (Number(i.value) || 0); }, 0);
    var circ = 2 * Math.PI * r;

    var box = X.h("div.chart-box");
    var svg = el("svg", {
      viewBox: "0 0 " + size + " " + size,
      preserveAspectRatio: "xMidYMid meet",
      style: "max-width:" + size + "px;margin:0 auto"
    });
    var g = el("g", { transform: "rotate(-90 " + cx + " " + cy + ")" });
    g.appendChild(el("circle", {
      cx: cx, cy: cy, r: r, fill: "none", stroke: "#f1f5f9", "stroke-width": thickness
    }));

    var tip = attachTip(box);
    var offset = 0;
    items.forEach(function (it, idx) {
      var value = Number(it.value) || 0;
      var frac = value / total;
      var color = it.color || PALETTE[idx % PALETTE.length];
      var arc = el("circle", {
        cx: cx, cy: cy, r: r, fill: "none", stroke: color, "stroke-width": thickness,
        "stroke-dasharray": (circ * frac - 1.5) + " " + circ,
        "stroke-dashoffset": -circ * offset,
        "stroke-linecap": "butt", style: "cursor:pointer;transition:stroke-width .12s"
      });
      arc.addEventListener("mouseenter", function () {
        arc.setAttribute("stroke-width", thickness + 4);
        var rb = svg.getBoundingClientRect();
        tip.show("<b>" + X.esc(it.label) + "</b><br>" + X.num(value) +
                 " · " + (frac * 100).toFixed(1) + "%", rb.width / 2, cy - r);
      });
      arc.addEventListener("mouseleave", function () {
        arc.setAttribute("stroke-width", thickness);
        tip.hide();
      });
      g.appendChild(arc);
      offset += frac;
    });
    svg.appendChild(g);

    // 圆心文字
    svg.appendChild(el("text", {
      x: cx, y: cy - 2, "text-anchor": "middle", fill: "#0f172a",
      "font-size": 22, "font-weight": 650
    }, opts.centerValue !== undefined ? String(opts.centerValue) : fmtTick(total)));
    svg.appendChild(el("text", {
      x: cx, y: cy + 15, "text-anchor": "middle", fill: "#94a3b8", "font-size": 11
    }, opts.centerLabel || "总计"));

    box.appendChild(svg);
    var wrap = X.h("div", null, [box]);
    if (opts.legend !== false) {
      wrap.appendChild(legend(items.map(function (it, idx) {
        return {
          label: it.label, color: it.color || PALETTE[idx % PALETTE.length],
          value: X.num(it.value) + " (" + ((Number(it.value) / total) * 100).toFixed(0) + "%)"
        };
      })));
    }
    return wrap;
  }

  /* ================================================================ 迷你趋势 */
  function sparkline(values, opts) {
    opts = opts || {};
    values = (values || []).map(Number);
    if (values.length < 2) return X.h("span.mut2.f-11", { text: "—" });
    var W = 100, H = opts.height || 26;
    var max = Math.max.apply(null, values), min = Math.min.apply(null, values);
    var range = max - min || 1;
    var pts = values.map(function (v, i) {
      return (i / (values.length - 1) * W).toFixed(2) + "," +
             (H - 2 - ((v - min) / range) * (H - 4)).toFixed(2);
    });
    var color = opts.color || PALETTE[0];
    var svg = el("svg", {
      viewBox: "0 0 " + W + " " + H, width: opts.width || 100, height: H,
      preserveAspectRatio: "none", style: "display:block"
    }, [
      el("polygon", {
        points: "0," + H + " " + pts.join(" ") + " " + W + "," + H,
        fill: color, opacity: 0.12
      }),
      el("polyline", {
        points: pts.join(" "), fill: "none", stroke: color, "stroke-width": 1.6,
        "stroke-linejoin": "round", "stroke-linecap": "round"
      })
    ]);
    return svg;
  }

  /* ================================================================ 分数量表 */
  /** 0-100 风险分的横向刻度条，标出四决策区间 */
  function scoreGauge(score, thresholds) {
    var t = thresholds || { pass: 30, mark: 60, review: 80 };
    var W = 400, H = 46;
    var segs = [
      { to: t.pass, color: "#16a34a", label: "通过" },
      { to: t.mark, color: "#0891b2", label: "标记" },
      { to: t.review, color: "#d97706", label: "人工审核" },
      { to: 100, color: "#dc2626", label: "拒绝" }
    ];
    var svg = svgRoot(W, H);
    var y = 16, bh = 9;
    var from = 0;
    segs.forEach(function (s) {
      var x = (from / 100) * W;
      var w = ((s.to - from) / 100) * W;
      svg.appendChild(el("rect", {
        x: x, y: y, width: w, height: bh, fill: s.color, opacity: 0.3,
        rx: from === 0 ? 4 : 0
      }));
      svg.appendChild(el("text", {
        x: x + w / 2, y: y + bh + 13, "text-anchor": "middle",
        fill: "#94a3b8", "font-size": 10
      }, s.label));
      from = s.to;
    });
    var sx = (Math.max(0, Math.min(100, Number(score) || 0)) / 100) * W;
    svg.appendChild(el("line", {
      x1: sx, y1: y - 5, x2: sx, y2: y + bh + 4, stroke: "#0f172a", "stroke-width": 2.4,
      "stroke-linecap": "round"
    }));
    svg.appendChild(el("text", {
      x: Math.max(12, Math.min(W - 12, sx)), y: y - 8, "text-anchor": "middle",
      fill: "#0f172a", "font-size": 11.5, "font-weight": 700
    }, String(Math.round(Number(score) || 0))));
    return X.h("div.chart-box", null, svg);
  }

  global.C = {
    PALETTE: PALETTE,
    line: lineChart,
    bar: barChart,
    hbar: hbarChart,
    donut: donutChart,
    sparkline: sparkline,
    scoreGauge: scoreGauge,
    legend: legend,
    empty: emptyChart
  };
})(window);
