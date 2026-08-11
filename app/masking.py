"""
敏感字段掩码工具 (2026-08-11 P1 脱敏).

用途:
  1. 日志脱敏: _safe_call 打日志前对 user_id/value 等参数掩码
  2. access log: 去掉 URL 查询串 (手机号/卡号常出现在 query param)
  3. LLM 上下文脱敏: query_business_data 返回前过滤姓名/诊断/收件人
"""
import logging


# 日志里需要整体掩码或半掩码的字段
_MASK_ALL_KEYS = {"value", "password", "api_key", "token", "secret"}
_MASK_PARTIAL_KEYS = {
    "phone_no", "medical_card_no", "id_card_hash", "receiver_name",
    "username", "user_id", "order_id",
}

# LLM 上下文里需要过滤的字段 (医疗明细: 姓名/诊断/收件人/卡号)
LLM_MASK_FIELDS = {
    "receiver_name", "diagnosis_name", "name",
    "phone_no", "medical_card_no", "id_card_hash",
}


def mask_value(value, keep_head: int = 2, keep_tail: int = 1) -> str:
    """半掩码: 保留头尾, 中间打 *; keep_head=0 且 keep_tail=0 时全掩."""
    s = str(value)
    if keep_head == 0 and keep_tail == 0:
        return "*" * min(len(s), 4)
    if len(s) <= keep_head + keep_tail:
        return "*" * len(s)
    return s[:keep_head] + "*" * min(4, len(s) - keep_head - keep_tail) + s[-keep_tail:]


def mask_kwargs(kwargs: dict) -> dict:
    """把日志用 kwargs 里的敏感字段掩码 (value/口令 全掩, user_id 等半掩)."""
    out = {}
    for k, v in kwargs.items():
        if k in _MASK_ALL_KEYS:
            out[k] = mask_value(v, 0, 0)
        elif k in _MASK_PARTIAL_KEYS:
            out[k] = mask_value(v)
        else:
            out[k] = v
    return out


def mask_business_row(row: dict) -> dict:
    """LLM 上下文脱敏: 把业务数据里的敏感字段替换为 **** (可配 settings.LLM_DATA_MASK)."""
    out = dict(row)
    for key in LLM_MASK_FIELDS:
        if key in out and out[key]:
            out[key] = "****"
    return out


class MaskQueryStringFilter(logging.Filter):
    """uvicorn access 日志过滤: 把 URL 里的查询串去掉 (防手机号/卡号落日志)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            args = list(record.args)
            changed = False
            for i, a in enumerate(args):
                if isinstance(a, str) and a.startswith("/") and "?" in a:
                    args[i] = a.split("?", 1)[0] + "?<masked>"
                    changed = True
            if changed:
                record.args = tuple(args)
        return True
