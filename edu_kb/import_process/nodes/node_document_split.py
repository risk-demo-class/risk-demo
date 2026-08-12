# -*- coding: utf-8 -*-
import json
import re
from pathlib import Path
from typing import Tuple, List, Dict

from edu_kb.config.config import chunk_config
from edu_kb.import_process.base import NodeBase
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.text_utils import split_text_by_size

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    RecursiveCharacterTextSplitter = None


class NodeDocumentSplit(NodeBase):
    """
    文档切分节点：按标题粗切 -> 长切短合精细化处理
    优先使用 langchain 递归切分器；未安装时回退到纯标准库实现。
    """

    name = "node_document_split"

    def __init__(self):
        super().__init__()
        self.chunk_config = chunk_config

    def process(self, state: ImportGraphState):
        content, file_title = self._step1_get_inputs(state)
        sections, title_count, lines_count = self._step2_split_by_titles(content, file_title)
        sections = self._step4_refine_chunks(sections)
        self._step5_print_stats(lines_count, sections)
        self._step6_backup(state, sections)
        return {"chunks": sections}

    def _step1_get_inputs(self, state: ImportGraphState) -> Tuple[str, str]:
        file_title = state.get("file_title")
        if not file_title:
            raise ValueError("文件标题不能为空")
        md_content = state.get("md_content")
        if not md_content:
            raise ValueError("文件内容不能为空")
        return md_content, file_title

    def _step2_split_by_titles(self, content, file_title):
        title_pattern = r"^\s*#{1,6}\s+.+"
        in_code_block = False
        code_fence = None
        current_lines = []
        sections = []
        current_title = ""
        title_count = 0

        def _flush_section():
            nonlocal title_count
            if not current_lines:
                return
            title_count += 1
            sections.append({
                "file_title": file_title,
                "title": current_title or "无标题",
                "content": "\n".join(current_lines),
            })

        content = content.replace("\r\n", "\n").replace("\r", "\n")
        lines = content.split("\n")
        for line in lines:
            stripped_line = line.strip()
            code_pattern = r"^(`{3,}|~{3,})"
            code_match = re.match(code_pattern, stripped_line)
            if code_match:
                marker = code_match.group(1)
                if not in_code_block:
                    in_code_block = True
                    code_fence = marker
                else:
                    if code_fence == marker:
                        in_code_block = False
                        code_fence = None

            is_valid_title = not in_code_block and re.match(title_pattern, stripped_line)
            if is_valid_title:
                _flush_section()
                current_title = stripped_line
                current_lines = [current_title]
            else:
                current_lines.append(stripped_line)

        _flush_section()
        logger.info(
            f"文档粗切完成，识别标题数量：{title_count}，共{len(sections)}个章节，文档共{len(lines)}行"
        )
        return sections, title_count, len(lines)

    def _step4_refine_chunks(self, sections: List[Dict[str, str]]) -> List[Dict[str, str]]:
        refined_split = []
        for sec in sections:
            refined_split.extend(self._split_long_section(sec))
        logger.info(f"切分超长章节完成，共{len(refined_split)}个chunk")

        final_sections = self._merge_short_sections(refined_split)
        logger.info(f"合并短章节完成，共{len(final_sections)}个chunk")

        for sec in final_sections:
            if not sec.get("parent_title"):
                sec["parent_title"] = sec.get("title")
                sec["part"] = 0
        logger.info(f"最后整理完成，共{len(final_sections)}个chunk")
        return final_sections

    def _step5_print_stats(self, lines_count, sections):
        logger.info("-" * 50 + " 文档切分统计信息 " + "-" * 50)
        logger.info(f"MD原始文本总行数：{lines_count}")
        logger.info(f"最终生成Chunk数量：{len(sections)}")

    def _step6_backup(self, state: ImportGraphState, sections: List[Dict[str, str]]) -> None:
        try:
            backup_path = Path(state.get("local_dir")) / state.get("file_title") / "chunks.json"
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(sections, f, ensure_ascii=False, indent=2)
            logger.info(f"Chunk结果备份成功，备份文件路径：{backup_path}")
        except Exception as e:
            logger.error(f"Chunk结果备份失败，错误信息：{e}")

    def _split_long_section(self, section: Dict[str, str]) -> List[Dict[str, str]]:
        content = section.get("content")
        if len(content) <= int(self.chunk_config.max_length):
            return [section]
        if "<table" in content.lower():
            return [section]

        title = section.get("title")
        prefix = f"{title}\n\n"
        available_len = int(self.chunk_config.max_length) - len(prefix)
        if available_len <= 0:
            logger.warning(f"章节标题过长，无法进行二次切分：{title}")
            return [section]

        body = content
        if title and body.startswith(title):
            body = body[body.find(title) + len(title):].lstrip()

        if RecursiveCharacterTextSplitter is not None:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=available_len,
                chunk_overlap=int(self.chunk_config.window_overlap),
                separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "],
            )
            split_texts = splitter.split_text(body)
        else:
            split_texts = split_text_by_size(
                body,
                max_length=available_len,
                overlap=int(self.chunk_config.window_overlap),
            )

        sub_sections = []
        for idx, chunk in enumerate(split_texts, start=1):
            text = chunk.strip()
            if not text:
                continue
            sub_sections.append({
                "title": f"{title} - {idx}",
                "content": prefix + text,
                "parent_title": title,
                "part": idx,
                "file_title": section.get("file_title"),
            })
        logger.info(f"章节{title}【二次切分】完成，共{len(sub_sections)}个子章节")
        return sub_sections

    def _merge_short_sections(self, sections: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if not sections:
            return []
        merged_sections = []
        current_chunk = None

        for sec in sections:
            if current_chunk is None:
                current_chunk = sec
                continue

            is_current_short = len(current_chunk["content"]) < int(self.chunk_config.min_length)
            is_same_parent = current_chunk.get("parent_title") == sec.get("parent_title")

            if is_current_short and is_same_parent:
                parent_title = sec.get("parent_title", "")
                next_content = sec.get("content")
                if parent_title and next_content.startswith(parent_title):
                    next_content = next_content[len(parent_title):].lstrip()
                current_chunk["content"] += "\n\n" + next_content
                current_chunk["title"] += "\n\n" + sec["title"]
                if "part" in sec:
                    current_chunk["part"] = sec["part"]
            else:
                merged_sections.append(current_chunk)
                current_chunk = sec

        if current_chunk is not None:
            merged_sections.append(current_chunk)
        return merged_sections
