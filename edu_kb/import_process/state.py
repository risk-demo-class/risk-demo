# -*- coding: utf-8 -*-
from typing import TypedDict, List, Dict


class ImportGraphState(TypedDict):
    """
    导入流程图状态：包含所有节点产生和消费的数据字段
    """
    task_id: str                  # 任务唯一 ID

    # 流程控制标记
    is_md_read_enabled: bool      # 是否走 Markdown 读取路径
    is_pdf_read_enabled: bool     # 是否走 PDF 读取路径
    is_docx_read_enabled: bool    # 是否走 docx 读取路径

    # 路径相关
    local_dir: str                # 当前工作目录 / 输出目录
    local_file_path: str          # 原始输入文件路径
    source_path: str              # 来源路径（原始目录信息）
    file_title: str               # 文件标题（文件名去后缀）
    pdf_path: str                 # PDF 文件路径（如果输入是 PDF）
    md_path: str                  # Markdown 文件路径

    # 教育元数据
    content_type: str             # 内容类型：course_intro / course_doc / project_doc / question
    course_name: str              # 课程名
    project_name: str             # 项目名
    question_bank_name: str       # 题库名

    # 内容数据
    md_content: str               # Markdown 全文内容
    chunks: List[Dict]            # 文档切片列表
    course_records: List[Dict]    # 课程介绍解析后的课程记录
    question_records: List[Dict]  # 题库解析后的题目记录
    entities: List[Dict]          # 知识实体：[{"name": str, "type": str, "source_file": str}]

    # 数据库关联
    embeddings_content: List[Dict]  # 包含向量的数据列表，准备写入 Milvus
