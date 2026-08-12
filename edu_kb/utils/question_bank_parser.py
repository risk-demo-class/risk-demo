# -*- coding: utf-8 -*-
"""
题库 Markdown 解析器（纯标准库）

数据格式（题目资料.md）：
    ## 题库名称
    - 题库编码: xxx

    ### 题目编码
    - **题型**: 单选题
    - **题干**: ...
    - **选项**:
    A. ...
    B. ...
    - **答案**: ...
    - **解析**: ...

题干 / 答案 / 解析可能是多行文本（例如编程题带代码块）。
"""
import re
from typing import List, Dict


def _parse_kv_line(line: str):
    m = re.match(r"^\s*-\s+\*\*([^*]+)\*\*\s*:\s*(.*)$", line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^\s*-\s+\*\*([^*]+)\*\*$", line)
    if m:
        return m.group(1).strip(), ""
    return None, None


def parse_question_bank(md_text: str, source_file: str = "") -> List[Dict]:
    """
    解析题库 Markdown，返回题目记录列表。
    每条记录包含：题库名、题库编码、题目编码、题型、题干、选项、答案、解析、来源文件名。
    """
    records: List[Dict] = []
    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    bank_name = ""
    bank_code = ""
    current = None
    current_key = None
    current_lines = []

    def flush_question():
        nonlocal current, current_key, current_lines
        if current is None:
            return
        question = {"question_code": current, "bank_name": bank_name, "bank_code": bank_code}

        for key, value_lines in current_lines:
            if key == "题型":
                question["question_type"] = "\n".join(value_lines).strip()
            elif key == "题干":
                question["question_text"] = "\n".join(value_lines).strip()
            elif key == "选项":
                options = []
                for opt_line in value_lines:
                    opt = opt_line.strip()
                    if not opt:
                        continue
                    if re.match(r"^[A-Ha-h][.、．)]", opt):
                        options.append(opt)
                    elif opt and options:
                        # 选项内容折行时追加到上一个选项
                        options[-1] = options[-1] + " " + opt
                question["options"] = options
            elif key == "答案":
                question["answer"] = "\n".join(value_lines).strip()
            elif key == "解析":
                question["analysis"] = "\n".join(value_lines).strip()

        question.setdefault("question_type", "")
        question.setdefault("question_text", "")
        question.setdefault("options", [])
        question.setdefault("answer", "")
        question.setdefault("analysis", "")
        question["source_file"] = source_file
        records.append(question)
        current = None
        current_key = None
        current_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("## "):
            flush_question()
            bank_name = stripped[3:].strip()
            bank_code = ""
            continue

        if stripped.startswith("### "):
            flush_question()
            current = stripped[4:].strip()
            current_key = None
            current_lines = []
            continue

        # 题库编码
        if bank_name and not stripped.startswith("###") and not stripped.startswith("##"):
            m = re.match(r"^\s*-\s*(题库编码)\s*:\s*(.+)$", stripped)
            if m:
                bank_code = m.group(2).strip()
                continue

        # 题目字段
        if current is not None:
            key, value = _parse_kv_line(line)
            if key:
                # 切换字段
                current_lines.append((key, [value] if value else []))
                current_key = key
            else:
                # 多行字段内容（题干中的代码块等）
                if current_key:
                    current_lines[-1] = (
                        current_key,
                        current_lines[-1][1] + [stripped],
                    )

    flush_question()
    return records


def build_question_search_text(question: Dict) -> str:
    """构造题目记录的向量化检索文本"""
    parts = [
        question.get("bank_name", ""),
        question.get("question_type", ""),
        question.get("question_text", ""),
        "\n".join(question.get("options", [])),
    ]
    return "\n".join(p for p in parts if p)
