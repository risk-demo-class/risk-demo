# -*- coding: utf-8 -*-
"""
课程介绍 Markdown 解析器（纯标准库）

数据格式（课程介绍.md）：
    ## 系列名称
    - **系列编码**: xxx
    - **描述**: ...
    - **课程分类**: ...
    - **适合人群**: ...
    - **学习目标**: ...
    - **适合年级**: ...

    ### 课程
    - **课程名**
      - 编码: xxx, 课时: 8, 学时: 16.00
      - 描述: ...
"""
import re
from typing import List, Dict


def _clean(value: str) -> str:
    return value.strip()


def _parse_kv_line(line: str):
    """解析 `- **key**: value` 或 `- key: value`"""
    m = re.match(r"^\s*-\s+\*\*([^*]+)\*\*\s*:\s*(.*)$", line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^\s*-\s+([^:：]+)\s*[:：]\s*(.*)$", line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None


def _parse_course_entry(course_name: str, lines: List[str]) -> Dict:
    """解析一门课程的明细行"""
    record = {
        "course_name": _clean(course_name),
        "course_code": "",
        "class_hours": "",
        "period": "",
        "description": "",
    }
    for line in lines:
        key, value = _parse_kv_line(line)
        if key is None:
            continue
        if key == "编码":
            # 编码: xxx, 课时: 8, 学时: 16.00
            is_first_part = True
            for part in re.split(r"[，,]", value):
                part = part.strip()
                km = re.match(r"^([^:：]+)\s*[:：]\s*(.*)$", part)
                if km:
                    k, v = km.group(1).strip(), km.group(2).strip()
                    if "编码" in k:
                        record["course_code"] = v
                    elif "课时" in k:
                        record["class_hours"] = v
                    elif "学时" in k:
                        record["period"] = v
                elif is_first_part and part:
                    # 形如 "general_purpose_programming_foundation_m1, 课时: 8, ..."
                    # 首段没有键名，直接作为课程编码
                    record["course_code"] = part
                is_first_part = False
        elif key == "描述":
            record["description"] = _clean(value)
    return record


def parse_course_intro(md_text: str, source_file: str = "") -> List[Dict]:
    """
    解析课程介绍 Markdown，返回课程记录列表。
    每条记录对应一门具体课程（继承所属系列的信息）。
    """
    records: List[Dict] = []
    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    series = None  # 当前系列信息
    in_course_section = False
    pending_course_name = None
    pending_course_lines = []

    def flush_course():
        nonlocal pending_course_name, pending_course_lines
        if pending_course_name and series:
            course = _parse_course_entry(pending_course_name, pending_course_lines)
            course.update({
                "series_name": series["series_name"],
                "series_code": series["series_code"],
                "category": series["category"],
                "suitable_for": series["suitable_for"],
                "goals": series["goals"],
                "grade": series["grade"],
                "series_description": series["description"],
                "source_file": source_file,
            })
            records.append(course)
        pending_course_name = None
        pending_course_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 系列标题
        if stripped.startswith("## "):
            flush_course()
            in_course_section = False
            series = {
                "series_name": stripped[3:].strip(),
                "series_code": "",
                "description": "",
                "category": "",
                "suitable_for": "",
                "goals": "",
                "grade": "",
            }
            continue

        # 课程小节
        if stripped.startswith("### "):
            flush_course()
            in_course_section = stripped[4:].strip() == "课程"
            continue

        # 系列元数据
        if series is not None and not in_course_section:
            key, value = _parse_kv_line(line)
            if key == "系列编码":
                series["series_code"] = value
            elif key == "描述":
                series["description"] = value
            elif key == "课程分类":
                series["category"] = value
            elif key == "适合人群":
                series["suitable_for"] = value
            elif key == "学习目标":
                series["goals"] = value
            elif key == "适合年级":
                series["grade"] = value
            continue

        # 课程列表：`- **课程名**`（或 `- **课程名**: 描述`）
        if in_course_section:
            m = re.match(r"^\s*-\s+\*\*(.+?)\*\*\s*(?::\s*(.*))?$", stripped)
            if m:
                flush_course()
                pending_course_name = m.group(1).strip()
                if m.group(2):
                    pending_course_lines.append(f"- 描述: {m.group(2).strip()}")
                continue

            # 课程明细行
            if pending_course_name:
                pending_course_lines.append(stripped)

    flush_course()
    return records


def build_course_search_text(course: Dict) -> str:
    """构造课程记录的向量化检索文本"""
    parts = [
        course.get("series_name", ""),
        course.get("course_name", ""),
        course.get("course_code", ""),
        course.get("category", ""),
        course.get("series_description", ""),
        course.get("description", ""),
        course.get("goals", ""),
        course.get("suitable_for", ""),
    ]
    return "\n".join(p for p in parts if p)
