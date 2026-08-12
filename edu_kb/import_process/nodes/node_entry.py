# -*- coding: utf-8 -*-
import os
from os.path import splitext

from edu_kb.config.constants import (
    CONTENT_TYPE_COURSE_INTRO,
    CONTENT_TYPE_COURSE_DOC,
    CONTENT_TYPE_PROJECT_DOC,
    CONTENT_TYPE_QUESTION,
)
from edu_kb.import_process.base import NodeBase
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.text_utils import strip_filename_version


def detect_content_type(file_title: str, local_file_path: str) -> str:
    """
    根据文件名与路径自动识别内容类型：
      - 课程介绍.md -> course_intro
      - 题目资料.md / *题库*.md -> question
      - 项目文档目录 / *项目*文档* -> project_doc
      - 课程文档目录 / 其余 -> course_doc
    """
    path_lower = local_file_path.replace("\\", "/").lower()

    if "课程介绍" in file_title:
        return CONTENT_TYPE_COURSE_INTRO
    if ("题目" in file_title and ("资料" in file_title or "题库" in file_title)) or "题库" in file_title:
        return CONTENT_TYPE_QUESTION
    if "项目文档" in path_lower or ("项目" in file_title and "文档" in file_title):
        return CONTENT_TYPE_PROJECT_DOC
    if "课程文档" in path_lower:
        return CONTENT_TYPE_COURSE_DOC
    return CONTENT_TYPE_COURSE_DOC


class NodeEntry(NodeBase):
    """入口节点：文件类型检查 + 内容类型识别 + 课程名兜底"""

    name = "node_entry"

    def process(self, state: ImportGraphState):
        logger.info(f"【{self.name}】程序的入口节点")

        # 1. 参数非空校验
        local_file_path = state.get("local_file_path")
        if not local_file_path:
            raise ValueError("请指定文件路径")

        # 2. 提取文件名称
        file_title = splitext(os.path.basename(local_file_path))[0]

        # 3. 内容类型识别
        content_type = detect_content_type(file_title, local_file_path)
        logger.info(f"内容类型识别：{content_type}（文件：{file_title}）")

        # 4. 课程名兜底（可从文件名推导，如 尚硅谷大模型技术之Python1.0.docx -> Python）
        course_name = ""
        if content_type in (CONTENT_TYPE_COURSE_DOC, CONTENT_TYPE_PROJECT_DOC):
            course_name = strip_filename_version(file_title)

        # 5. 文件类型检查
        if local_file_path.endswith(".pdf"):
            logger.info(f"PDF文件检查：{local_file_path}")
            return {
                "is_pdf_read_enabled": True,
                "pdf_path": local_file_path,
                "file_title": file_title,
                "content_type": content_type,
                "course_name": course_name,
                "source_path": local_file_path,
            }
        elif local_file_path.endswith(".docx"):
            logger.info(f"docx文件检查：{local_file_path}")
            return {
                "is_docx_read_enabled": True,
                "file_title": file_title,
                "content_type": content_type,
                "course_name": course_name,
                "source_path": local_file_path,
            }
        elif local_file_path.endswith(".md"):
            logger.info(f"MD文件检查：{local_file_path}")
            return {
                "is_md_read_enabled": True,
                "md_path": local_file_path,
                "file_title": file_title,
                "content_type": content_type,
                "course_name": course_name,
                "source_path": local_file_path,
            }
        else:
            current_type = local_file_path.rsplit(".", 1)[-1] if "." in local_file_path else "未知"
            raise ValueError(f"不支持的文件类型：{current_type}")
