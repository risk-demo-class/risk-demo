# Bank Frontend De-Ecommerce Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every user-facing page describe and operate a retail-bank risk-control workflow, with no e-commerce terminology or behavior in the web UI.

**Architecture:** Keep FastAPI, Jinja2, Bootstrap, and current API routes. Replace only presentation copy, form guidance, business-field mappings, and dashboard-facing metadata; use a compact navy-and-cyan banking operations style defined centrally in `base.html`.

**Tech Stack:** FastAPI, Jinja2, Bootstrap 5, Bootstrap Icons, Chart.js, vanilla JavaScript.

## Global Constraints

- Do not add frontend dependencies.
- Retain all existing URL routes and API payload shapes.
- Use Chinese banking terminology: 交易、转账、贷款申请、登录、设备、IP、银行卡号、身份证号。
- Preserve keyboard labels, visible focus states, and responsive behavior.
- Do not expose genuine card or identity values; display hashes where relevant.

---

### Task 1: Add a regression guard for e-commerce copy

**Files:**
- Modify: `tests/test_bank_assets.py`
- Test: `tests/test_bank_assets.py`

- [ ] **Step 1: Write the failing test**

```python
def test_user_facing_frontend_has_no_ecommerce_terms():
    for path in FRONTEND_FILES:
        text = path.read_text(encoding="utf-8")
        assert "电商" not in text
        assert "订单" not in text
        assert "售后" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bank_assets.py::test_user_facing_frontend_has_no_ecommerce_terms -q`

- [ ] **Step 3: Replace visible copy and mapped labels**

Modify every listed template and `static/app.js`; preserve business API field names where required but never display e-commerce words.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bank_assets.py::test_user_facing_frontend_has_no_ecommerce_terms -q`

### Task 2: Establish the banking operations visual system

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Apply central visual tokens**

Use navy surfaces, cyan interaction accents, risk-state semantic colors, a compact desktop sidebar, responsive mobile navigation, visible `:focus-visible` outlines, and `prefers-reduced-motion` support.

- [ ] **Step 2: Verify all pages inherit the system**

Run: `python -m pytest tests/test_base_layout.py -q`

### Task 3: Align operational pages with banking workflow

**Files:**
- Modify: `templates/dashboard.html`
- Modify: `templates/risk_check.html`
- Modify: `templates/cases.html`
- Modify: `templates/assessments.html`
- Modify: `templates/rules.html`
- Modify: `templates/blacklist.html`
- Modify: `templates/chat.html`

- [ ] **Step 1: Replace all e-commerce entities with bank entities**

Use transaction/loan/login IDs, transaction frequency, account and device risk, and five bank blacklist types. Preserve API fields but map old compatibility profile values to neutral bank-facing labels.

- [ ] **Step 2: Run focused frontend content tests**

Run: `python -m pytest tests/test_bank_assets.py tests/test_risk_check_page.py tests/test_base_layout.py -q`

### Task 4: Align user-visible application and assistant metadata

**Files:**
- Modify: `scripts/main.py`
- Modify: `app/agent/chat.py`
- Modify: `static/app.js`

- [ ] **Step 1: Replace title, descriptions, prompts, and public JavaScript header**

Use “银行风控系统” language and bank events.

- [ ] **Step 2: Verify application import and copy guard**

Run: `python -m pytest tests/test_bank_scripts.py tests/test_bank_assets.py -q`

### Task 5: Final verification

- [ ] **Step 1: Scan user-facing code for forbidden e-commerce words**

Run: `rg -n "电商|订单|售后|收货|地址|手机号|物流|商品|退款|投诉" templates static app/agent/chat.py scripts/main.py`

- [ ] **Step 2: Run all relevant tests**

Run: `python -m pytest tests/test_bank_assets.py tests/test_bank_contract.py tests/test_bank_scripts.py tests/test_base_layout.py tests/test_risk_check_page.py -q -p no:cacheprovider`

- [ ] **Step 3: Confirm application can import**

Run: `python -c "from scripts.main import app; print(app.title)"`
