const scenarios = {
  normal: { sourceId: "ENR-NORMAL-001", userId: "STU-NORMAL-001" },
  review: { sourceId: "ENR-RISK-001", userId: "STU-RISK-01" },
  blocked: { sourceId: "ENR-BLACK-001", userId: "STU-BLACK-001" },
};

const form = document.querySelector("#risk-form");
const sourceId = document.querySelector("#source-id");
const userId = document.querySelector("#user-id");
const eventType = document.querySelector("#event-type");
const submitButton = document.querySelector("#submit-button");
const emptyState = document.querySelector("#result-empty");
const resultContent = document.querySelector("#result-content");
const resultState = document.querySelector("#result-state");
const decisionSummary = document.querySelector(".decision-summary");
const errorMessage = document.querySelector("#form-error");

function decisionTone(decision) {
  if (decision === "通过") return "pass";
  if (decision === "人工审核") return "review";
  return "reject";
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.querySelector("span").textContent = isLoading ? "正在核验…" : "执行风险核验";
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function clearError() {
  errorMessage.textContent = "";
  errorMessage.hidden = true;
}

function renderRules(rules) {
  const rulesList = document.querySelector("#rules-list");
  rulesList.replaceChildren();
  if (rules.length === 0) {
    const item = document.createElement("li");
    item.textContent = "本次未命中规则";
    rulesList.append(item);
    return;
  }
  rules.forEach((rule) => {
    const item = document.createElement("li");
    const name = document.createElement("span");
    const score = document.createElement("span");
    name.textContent = `${rule.rule_id} · ${rule.rule_name}`;
    score.className = "rule-score";
    score.textContent = `+${rule.risk_score}`;
    item.append(name, score);
    rulesList.append(item);
  });
}

function renderResult(result) {
  const tone = decisionTone(result.decision);
  emptyState.hidden = true;
  resultContent.hidden = false;
  decisionSummary.dataset.tone = tone;
  resultState.className = `result-state result-state--${tone}`;
  resultState.textContent = result.decision;
  document.querySelector("#decision-value").textContent = result.decision;
  document.querySelector("#score-value").textContent = result.final_score;
  document.querySelector("#risk-level-value").textContent = result.risk_level;
  document.querySelector("#rule-count-value").textContent = `${result.rule_count} 条`;
  document.querySelector("#event-id-value").textContent = result.event_id;
  document.querySelector("#assessment-id-value").textContent = result.assessment_id;
  renderRules(result.triggered_rules);

  const blockedMessage = document.querySelector("#blocked-message");
  blockedMessage.hidden = !result.blocked_by;
  blockedMessage.textContent = result.blocked_by ? `已在规则计算前拦截：${result.blocked_by}` : "";
}

async function submitRiskCheck() {
  clearError();
  const payload = {
    event_type: eventType.value,
    source_id: sourceId.value.trim(),
    user_id: userId.value.trim(),
  };
  if (!payload.source_id || !payload.user_id) {
    showError("请填写报名编号和学生编号后再核验。");
    return;
  }

  setLoading(true);
  try {
    const response = await fetch("/api/risk/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.detail || "风险核验失败，请检查输入。 ");
    }
    renderResult(body);
  } catch (error) {
    showError(error instanceof Error ? error.message : "风险核验失败，请稍后重试。");
  } finally {
    setLoading(false);
  }
}

document.querySelectorAll("[data-scenario]").forEach((button) => {
  button.addEventListener("click", () => {
    const scenario = scenarios[button.dataset.scenario];
    sourceId.value = scenario.sourceId;
    userId.value = scenario.userId;
    sourceId.focus();
  });
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitRiskCheck();
});
