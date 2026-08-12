const PP = {
  async get(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
    return response.json();
  },
  async post(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
    return response.json();
  },
  money(value, currency = "USD") {
    return new Intl.NumberFormat("zh-CN", { style: "currency", currency, maximumFractionDigits: 2 }).format(value || 0);
  },
  time(value) {
    return value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "-";
  },
  escape(value) {
    const element = document.createElement("span");
    element.textContent = value ?? "";
    return element.innerHTML;
  },
  state(target, type, message) {
    target.innerHTML = `<div class="${type}">${this.escape(message)}</div>`;
  },
};

