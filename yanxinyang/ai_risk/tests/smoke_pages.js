/* 前端页面渲染冒烟测试（零依赖，Node 内建最小 DOM 桩）
 *
 * 用途：不开浏览器就能验证 12 个页面模块是否能在真实 API 数据上完成渲染。
 * 运行：node tests/smoke_pages.js   （需先启动服务 python _run.py）
 *
 * 原理：实现足够用的 document/Element/fetch/EventSource 桩，逐页调用
 *       window.__PAGES__[key](viewEl)，等待微任务队列排空后检查是否抛错。
 */
"use strict";

const fs = require("fs");
const path = require("path");
const http = require("http");

const ROOT = path.resolve(__dirname, "..");
const BASE = "http://127.0.0.1:8000";
const errors = [];

/* ---------------------------------------------------------------- DOM 桩 */
let nodeSeq = 0;

class ClassList {
  constructor(el) { this.el = el; }
  add(...cs) { cs.forEach((c) => { if (c && !this.el._cls.includes(c)) this.el._cls.push(c); }); }
  remove(...cs) { cs.forEach((c) => { const i = this.el._cls.indexOf(c); if (i >= 0) this.el._cls.splice(i, 1); }); }
  toggle(c, on) { if (on === undefined) on = !this.contains(c); on ? this.add(c) : this.remove(c); return on; }
  contains(c) { return this.el._cls.includes(c); }
}

/* Node 基类：浏览器里 Element 与 Text 都是 Node 的实例，
   core.js 的 appendChildren 用 `children instanceof Node` 判断，桩必须还原这层继承。 */
class NodeBase {}

class Element extends NodeBase {
  constructor(tag) {
    super();
    this.tagName = String(tag || "div").toUpperCase();
    this.childNodes = [];
    this.parentNode = null;
    this.style = {};
    this.dataset = {};
    this._cls = [];
    this._attrs = {};
    this._listeners = {};
    this._text = "";
    this._id = ++nodeSeq;
    this.classList = new ClassList(this);
  }
  get children() { return this.childNodes.filter((n) => n instanceof Element); }
  get firstChild() { return this.childNodes[0] || null; }
  get className() { return this._cls.join(" "); }
  set className(v) { this._cls = String(v || "").split(/\s+/).filter(Boolean); }
  get textContent() {
    if (this.childNodes.length) {
      return this.childNodes.map((n) => (n instanceof Element ? n.textContent : String(n.data || ""))).join("");
    }
    return this._text;
  }
  set textContent(v) { this.childNodes = []; this._text = v == null ? "" : String(v); }
  get innerHTML() { return this.textContent; }
  set innerHTML(v) {
    this.childNodes = [];
    // 只需还原实体解码，页面里 html: 属性仅用于 &nbsp; 之类的排版占位
    this._text = v == null ? "" : String(v)
      .replace(/&nbsp;/g, "\u00a0").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
  }
  get value() { return this._attrs.value == null ? "" : this._attrs.value; }
  set value(v) { this._attrs.value = v == null ? "" : String(v); }
  appendChild(n) {
    if (n == null) return n;
    if (n && n.__frag) { n.childNodes.slice().forEach((c) => this.appendChild(c)); return n; }
    if (n.parentNode) n.parentNode.removeChild(n);
    n.parentNode = this; this.childNodes.push(n); return n;
  }
  append(...ns) { ns.forEach((n) => this.appendChild(typeof n === "string" ? document.createTextNode(n) : n)); }
  insertBefore(n, ref) {
    const i = this.childNodes.indexOf(ref);
    if (i < 0) return this.appendChild(n);
    n.parentNode = this; this.childNodes.splice(i, 0, n); return n;
  }
  removeChild(n) { const i = this.childNodes.indexOf(n); if (i >= 0) { this.childNodes.splice(i, 1); n.parentNode = null; } return n; }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  setAttribute(k, v) { this._attrs[k] = String(v); if (k === "class") this.className = v; }
  getAttribute(k) { return this._attrs[k] == null ? null : this._attrs[k]; }
  removeAttribute(k) { delete this._attrs[k]; }
  hasAttribute(k) { return k in this._attrs; }
  addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); }
  removeEventListener(t, fn) {
    const a = this._listeners[t]; if (!a) return;
    const i = a.indexOf(fn); if (i >= 0) a.splice(i, 1);
  }
  dispatchEvent(ev) {
    (this._listeners[ev.type] || []).forEach((fn) => { try { fn.call(this, ev); } catch (e) { errors.push("[event " + ev.type + "] " + e.message); } });
    if (this["on" + ev.type]) { try { this["on" + ev.type].call(this, ev); } catch (e) { errors.push("[on" + ev.type + "] " + e.message); } }
    return true;
  }
  click() { this.dispatchEvent({ type: "click", target: this, preventDefault() {}, stopPropagation() {} }); }
  focus() {} blur() {} scrollIntoView() {}
  _all() { const out = []; const walk = (n) => n.childNodes.forEach((c) => { if (c instanceof Element) { out.push(c); walk(c); } }); walk(this); return out; }
  _match(sel) {
    sel = sel.trim();
    if (sel.startsWith("#")) return this._attrs.id === sel.slice(1);
    if (sel.startsWith(".")) return sel.slice(1).split(".").every((c) => this.classList.contains(c));
    if (sel.startsWith("[")) { const m = /^\[([\w-]+)(?:=["']?([^"'\]]*)["']?)?\]$/.exec(sel); if (!m) return false;
      return m[2] === undefined ? this.hasAttribute(m[1]) : this._attrs[m[1]] === m[2]; }
    const parts = sel.split(/(?=[.#\[])/);
    return parts.every((p, i) => (i === 0 ? this.tagName === p.toUpperCase() : this._match(p)));
  }
  querySelector(sel) { return this._all().find((n) => sel.split(",").some((s) => n._match(s))) || null; }
  querySelectorAll(sel) { return this._all().filter((n) => sel.split(",").some((s) => n._match(s))); }
  get offsetWidth() { return 800; } get clientWidth() { return 800; }
  get scrollHeight() { return 400; } set scrollTop(v) {} get scrollTop() { return 0; }
  getBoundingClientRect() { return { width: 800, height: 400, top: 0, left: 0, right: 800, bottom: 400 }; }
}

class TextNode extends NodeBase {
  constructor(d) { super(); this.data = String(d); this.nodeType = 3; this.parentNode = null; }
  get textContent() { return this.data; }
}

const document = {
  createElement: (t) => new Element(t),
  createElementNS: (ns, t) => new Element(t),
  createTextNode: (d) => new TextNode(d),
  createDocumentFragment() { const f = new Element("fragment"); f.__frag = true; return f; },
  body: new Element("body"),
  documentElement: new Element("html"),
  addEventListener() {}, removeEventListener() {},
  querySelector(s) { return document.body.querySelector(s); },
  querySelectorAll(s) { return document.body.querySelectorAll(s); },
  getElementById(id) { return document.body.querySelector("#" + id); }
};
document.body.setAttribute("id", "body");

/* ---------------------------------------------------------------- fetch 桩（转 http 真实请求） */
function fetchStub(url, opts) {
  opts = opts || {};
  const full = url.startsWith("http") ? url : BASE + url;
  return new Promise((resolve, reject) => {
    const u = new URL(full);
    const req = http.request({
      hostname: u.hostname, port: u.port || 80, path: u.pathname + u.search,
      method: opts.method || "GET", headers: opts.headers || {}
    }, (res) => {
      let buf = "";
      res.setEncoding("utf8");
      res.on("data", (c) => { buf += c; });
      res.on("end", () => resolve({
        ok: res.statusCode >= 200 && res.statusCode < 300,
        status: res.statusCode,
        headers: { get: (k) => res.headers[String(k).toLowerCase()] || null },
        json: () => Promise.resolve(JSON.parse(buf || "{}")),
        text: () => Promise.resolve(buf),
        body: null
      }));
    });
    req.on("error", reject);
    if (opts.body) req.write(opts.body);
    req.end();
  });
}

/* ---------------------------------------------------------------- window 桩 */
const timers = [];
global.window = {
  document, location: { hash: "", pathname: "/", href: BASE + "/", search: "" },
  addEventListener() {}, removeEventListener() {},
  setTimeout: (fn, ms) => { const t = setTimeout(fn, Math.min(ms || 0, 5)); timers.push(t); return t; },
  clearTimeout, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: (fn) => setTimeout(fn, 0),
  fetch: fetchStub, matchMedia: () => ({ matches: false, addListener() {} }),
  navigator: { clipboard: { writeText: () => Promise.resolve() }, userAgent: "node" },
  innerWidth: 1440, innerHeight: 900,
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
  AbortController: global.AbortController,
  console
};
global.document = document;
global.location = window.location;
global.fetch = fetchStub;
try { Object.defineProperty(global, "navigator", { value: window.navigator, configurable: true }); } catch (e) { /* Node 22 内建 navigator 只读，忽略 */ }
global.HTMLElement = Element;
global.Element = Element;
global.Node = NodeBase;
global.Text = TextNode;
global.getComputedStyle = window.getComputedStyle;
global.requestAnimationFrame = window.requestAnimationFrame;
global.alert = () => {};
global.matchMedia = window.matchMedia;

window.__APP__ = { name: "智学安·教育风控平台（教学版）", version: "3.0", routerCount: 10, endpointCount: 30, pages: [] };

/* ---------------------------------------------------------------- 加载脚本 */
const FILES = ["core.js", "charts.js", "pages-monitor.js", "pages-handle.js", "pages-insight.js", "pages-system.js", "app.js"];

// PAGES 与后端 scripts/main.py 保持一致
window.__APP__.pages = [
  { key: "dashboard", title: "风控总览", icon: "gauge", group: "监控" },
  { key: "check", title: "实时检测", icon: "shield", group: "监控" },
  { key: "assessment", title: "评估历史", icon: "history", group: "监控" },
  { key: "case", title: "案件处置", icon: "folder", group: "处置" },
  { key: "rule", title: "规则管理", icon: "rules", group: "处置" },
  { key: "blacklist", title: "黑名单", icon: "ban", group: "处置" },
  { key: "profile", title: "用户画像", icon: "user", group: "洞察" },
  { key: "business", title: "业务数据", icon: "table", group: "洞察" },
  { key: "assistant", title: "AI 助手", icon: "robot", group: "洞察" },
  { key: "model", title: "模型中心", icon: "brain", group: "系统" },
  { key: "config", title: "配置中心", icon: "cog", group: "系统" },
  { key: "audit", title: "审计日志", icon: "log", group: "系统" }
];

// app.js 需要的 DOM 骨架
// 与 web/templates/index.html 的 id 清单保持一致
["nav", "view", "toast-wrap", "modal-mask", "modal-title", "modal-body", "modal-foot",
 "modal-close", "page-title", "page-desc", "model-pill", "model-pill-text",
 "health-pill", "health-pill-text", "sf-routers", "sf-endpoints",
 "btn-refresh", "btn-menu", "sidebar"].forEach((id) => {
  const el = new Element("div");
  el.setAttribute("id", id);
  document.body.appendChild(el);
});

const vm = require("vm");
const ctx = vm.createContext(global);
global.window.window = global.window;
FILES.forEach((f) => {
  const p = path.join(ROOT, "web/static/js", f);
  const code = fs.readFileSync(p, "utf8");
  try {
    vm.runInThisContext(code, { filename: f });
  } catch (e) {
    errors.push("[load " + f + "] " + e.message + "\n" + String(e.stack).split("\n").slice(0, 4).join("\n"));
  }
});

/* ---------------------------------------------------------------- 逐页渲染 */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const reg = window.Pages || {};
  const keys = Object.keys(reg);
  console.log("已注册页面模块：" + keys.length + " → " + keys.join(", "));
  const expected = window.__APP__.pages.map((p) => p.key);
  const missing = expected.filter((k) => !keys.includes(k));
  if (missing.length) errors.push("[registry] 缺少页面模块：" + missing.join(", "));

  for (const key of expected) {
    const fn = reg[key];
    if (typeof fn !== "function") { console.log("SKIP  " + key + " （未注册）"); continue; }
    const view = new Element("div");
    view.setAttribute("id", "view");
    const before = errors.length;
    try {
      fn(view);
      await sleep(700);           // 等 fetch + 渲染
    } catch (e) {
      errors.push("[render " + key + "] " + e.message + "\n" + String(e.stack).split("\n").slice(0, 5).join("\n"));
    }
    const txt = view.textContent || "";
    const nodes = view._all().length;
    const bad = errors.length > before;
    const emptyish = nodes < 5;
    console.log((bad ? "FAIL  " : emptyish ? "THIN  " : "OK    ") +
      key.padEnd(12) + " 节点 " + String(nodes).padStart(5) + " | " + txt.replace(/\s+/g, " ").slice(0, 72));
    if (emptyish && !bad) errors.push("[render " + key + "] 渲染节点过少(" + nodes + ")，可能未产出内容");
  }

  await sleep(300);
  console.log("\n================ 结果 ================");
  if (errors.length) {
    console.log("发现 " + errors.length + " 个问题：");
    errors.forEach((e, i) => console.log("\n" + (i + 1) + ") " + e));
    process.exitCode = 1;
  } else {
    console.log("全部 12 个页面渲染通过，无运行时错误。");
  }
  timers.forEach(clearTimeout);
  process.exit(errors.length ? 1 : 0);
})();
