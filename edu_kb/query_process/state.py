# -*- coding: utf-8 -*-
from typing import TypedDict, List


class QueryGraphState(TypedDict):
    """
    查询流程图状态：包含整个查询流程中传递的所有数据。
    """

    task_id: str                  # 任务 ID
    session_id: str               # 会话 ID

    original_query: str           # 用户原始问题
    intent: str                   # 查询意图：course_intro / course_detail / doc_retrieval / question / qa
    rewritten_query: str          # 改写后的问题

    # 提取/确认的知识实体
    course_names: List[str]       # 确认的课程名
    project_names: List[str]      # 确认的项目名
    bank_names: List[str]         # 确认的题库名
    knowledge_points: List[str]   # 知识点关键词

    # 检索过程中的中间数据
    course_results: list          # 课程检索结果（edu_courses）
    question_results: list        # 题目检索结果（edu_questions）
    embedding_chunks: list        # 普通向量检索回来的切片
    hyde_embedding_chunks: list   # HyDE 检索回来的切片
    web_search_docs: list         # 网络搜索回来的文档

    # 排序过程中的数据
    rrf_chunks: list              # RRF 融合排序后的切片
    reranked_docs: list           # 重排序后的最终 Top-K 文档

    # 生成过程中的数据
    prompt: str                   # 组装好的 Prompt
    answer: str                   # 最终生成的答案
    references: list              # 引用信息（课程/项目/章节/文件/题库/题目编码）

    # 辅助信息
    history: list                 # 历史对话记录
    is_stream: bool               # 是否流式输出
