const form = document.getElementById("login-form");
const errorBox = document.getElementById("login-error");
const submit = document.getElementById("login-submit");

try {
  const response = await fetch("/api/auth/me");
  if (response.ok) location.replace("/");
} catch (_) { /* service availability is handled on submit */ }

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.textContent = "";
  submit.disabled = true;
  submit.textContent = "正在登录…";
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("username").value.trim(),
        password: document.getElementById("password").value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "登录失败");
    const next = new URLSearchParams(location.search).get("next");
    location.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
  } catch (error) {
    errorBox.textContent = error.message || "暂时无法登录，请稍后重试";
    submit.disabled = false;
    submit.textContent = "登录";
  }
});
