# -*- coding: utf-8 -*-
"""
纯标准库文本处理工具（用于无 langchain 依赖的兜底切分）
"""
import re
import os
from typing import List


def split_text_by_size(
        text: str,
        max_length: int = 1200,
        overlap: int = 100,
        separators=None,
) -> List[str]:
    """
    按最大长度与重叠窗口切分文本（langchain RecursiveCharacterTextSplitter 的简化版）。
    优先在分隔符处切分；无法切分时按字符硬切。
    """
    if separators is None:
        separators = ["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "]
    if not text:
        return []
    if len(text) <= max_length:
        return [text]

    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_length, length)
        if end < length:
            # 在 [start+max_length*2//3, end] 区间内寻找最后一个分隔符
            best_pos = -1
            best_len = 0
            search_start = start + max_length * 2 // 3
            for sep in separators:
                pos = text.rfind(sep, search_start, end)
                if pos > best_pos:
                    best_pos = pos
                    best_len = len(sep)
            if best_pos > start:
                end = best_pos + best_len
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(end - overlap, start + 1)
    return chunks


def dedupe_preserve_order(items: List[str]) -> List[str]:
    """去重并保持顺序"""
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def strip_filename_version(filename: str) -> str:
    """
    从文件名中提取课程名：
    "尚硅谷大模型技术之Python1.0.docx" -> "Python"
    """
    # 去掉扩展名（兼容传入 .docx / .md 等带后缀的文件名）
    name = os.path.splitext(filename)[0]
    for prefix in ("尚硅谷大模型技术之", "尚硅谷大模型技术之 ", "尚硅谷大模型技术-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    # 去掉版本号（如 1.0 / 1.4.0 / 2.0.0 / v1.1.7）
    name = re.sub(r"[vV]?\d+(\.\d+)*\s*$", "", name)
    # 去掉常见后缀描述
    name = re.sub(r"[（(].*?[)）]$", "", name)
    return name.strip()
