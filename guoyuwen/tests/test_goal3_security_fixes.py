"""Goal 3 安全修复回归：5 处存储型 XSS 转义 + 训练标签自举防护。

全部离线运行，不依赖 MySQL；用于防止再次把用户可控值直接拼进 innerHTML /
内联事件，以及防止生成训练数据时旧模型污染规则决策。
"""

from pathlib import Path

from app.engine import ml_model

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


# ============================================================
# 1. 共享 escapeHtml 已注入 app.js（所有页面都加载它）
# ============================================================


def test_global_escape_html_is_defined_in_app_js():
    app_js = _read("static/app.js")
    assert "function escapeHtml(value)" in app_js
    assert "&#39;" in app_js  # 单引号必须转义，防止内联/属性注入


# ============================================================
# 2. rules.html：文本转义 + 内联事件改 data-* 委托
# ============================================================


def test_rules_table_escapes_rule_fields():
    html = _read("templates/rules.html")
    assert "${escapeHtml(r.rule_id)}" in html
    assert "${escapeHtml(r.rule_name)}" in html
    assert "${escapeHtml(r.rule_category)}" in html
    assert "${escapeHtml(r.action)}" in html


def test_rules_table_no_inline_handler_with_rule_id():
    html = _read("templates/rules.html")
    # 用户可控 rule_id 不得进内联事件
    assert "onchange=\"toggleRule('${r.rule_id}')\"" not in html
    assert "onclick=\"editRule('${r.rule_id}')\"" not in html
    assert "onclick=\"deleteRule('${r.rule_id}')\"" not in html
    # 改走 data-* + 委托
    assert 'data-rule-id="${escapeHtml(r.rule_id)}"' in html
    assert "tbody.addEventListener('click'" in html


# ============================================================
# 3. cases.html：文本转义 + 重做检查不再拼内联事件
# ============================================================


def test_cases_table_escapes_user_fields_and_uses_data_attributes():
    html = _read("templates/cases.html")
    assert "${escapeHtml(c.user_id)}" in html
    assert "${escapeHtml(c.case_category || '-')}" in html
    assert "${escapeHtml(c.review_comment)}" in html
    assert 'data-source-id="${escapeHtml(c.source_id)}"' in html
    assert 'data-action="recheck"' in html
    assert "onclick=\"recheckCase('${c.case_id}','${c.source_id}','${c.user_id}'" not in html
    assert "bindCaseTableActions" in html


# ============================================================
# 4. blacklist.html：reason 与脱敏值转义
# ============================================================


def test_blacklist_escapes_reason_and_masked_value():
    html = _read("templates/blacklist.html")
    assert "${escapeHtml(maskValue(it.blacklist_type, it.blacklist_value))}" in html
    assert "${it.reason ? escapeHtml(it.reason) :" in html
    assert "${it.reason ||" not in html  # 旧的未转义写法已删除


# ============================================================
# 5. assessments.html：event_data 与规则字段转义
# ============================================================


def test_assessments_escapes_event_data_and_rule_fields():
    html = _read("templates/assessments.html")
    assert "escapeHtml(JSON.stringify(JSON.parse(a.event_data)" in html
    assert "${escapeHtml(a.event_source_id || '-')}" in html
    assert "${escapeHtml(r.rule_name)}" in html
    # 不允许 event_data 原样进 <pre>
    assert "<pre class=\"bg-light p-2 small\">${a.event_data}</pre>" not in html


# ============================================================
# 6. chat.html：先转义再套 markdown
# ============================================================


def test_chat_escapes_before_markdown_replace():
    html = _read("templates/chat.html")
    assert "let html = escapeHtml(content)" in html
    # 转义必须在 markdown 替换之前
    esc_pos = html.find("escapeHtml(content)")
    replace_pos = html.find(".replace(/\\n/g")
    assert 0 <= esc_pos < replace_pos


# ============================================================
# 7. gen_train_dataset：生成时强制纯规则（标签自举防护）
# ============================================================


def test_gen_train_dataset_uses_ml_disabled():
    script = _read("scripts/gen_train_dataset.py")
    assert "ml_model.disabled()" in script


def test_ml_disabled_context_forces_pure_rule_decision():
    """模型已加载时，disabled() 内 is_model_loaded 恒 False、load_model 提前返回。"""
    saved_loaded = ml_model._LOADED
    saved_model = ml_model._MODEL
    saved_gen = ml_model._generation_mode
    try:
        ml_model._LOADED = True
        ml_model._MODEL = object()  # 模拟已加载的 booster
        ml_model._generation_mode = False

        with ml_model.disabled():
            assert ml_model.is_model_loaded() is False
            assert ml_model.load_model("whatever_path") is False
            assert ml_model.predict({}) is not None  # 兜底 MlResult，不抛异常

        # 退出后恢复原状态
        assert ml_model.is_model_loaded() is True
    finally:
        ml_model._LOADED = saved_loaded
        ml_model._MODEL = saved_model
        ml_model._generation_mode = saved_gen


def test_ml_disabled_is_reentrant_and_restores():
    saved_gen = ml_model._generation_mode
    try:
        ml_model._generation_mode = False
        with ml_model.disabled():
            assert ml_model._generation_mode is True
        assert ml_model._generation_mode is False
    finally:
        ml_model._generation_mode = saved_gen
