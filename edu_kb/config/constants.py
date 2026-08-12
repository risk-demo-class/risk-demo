# -*- coding: utf-8 -*-
"""
教育知识库全局常量
"""

# ---------------------------
# 内容类型（导入 / 检索共用）
# ---------------------------
CONTENT_TYPE_COURSE_INTRO = "course_intro"      # 课程介绍
CONTENT_TYPE_COURSE_DOC = "course_doc"          # 课程文档（讲义）
CONTENT_TYPE_PROJECT_DOC = "project_doc"        # 项目文档
CONTENT_TYPE_QUESTION = "question"              # 题库题目

CONTENT_TYPE_CN = {
    CONTENT_TYPE_COURSE_INTRO: "课程介绍",
    CONTENT_TYPE_COURSE_DOC: "课程文档",
    CONTENT_TYPE_PROJECT_DOC: "项目文档",
    CONTENT_TYPE_QUESTION: "题库题目",
}

# ---------------------------
# 查询意图
# ---------------------------
INTENT_COURSE_INTRO = "course_intro"    # 课程介绍 / 课程列表
INTENT_COURSE_DETAIL = "course_detail"  # 课程详情
INTENT_DOC_RETRIEVAL = "doc_retrieval"  # 文档片段检索
INTENT_QUESTION = "question"            # 题目检索
INTENT_QA = "qa"                        # 知识问答

INTENT_CN = {
    INTENT_COURSE_INTRO: "课程介绍",
    INTENT_COURSE_DETAIL: "课程详情",
    INTENT_DOC_RETRIEVAL: "文档检索",
    INTENT_QUESTION: "题目检索",
    INTENT_QA: "知识问答",
}

# ---------------------------
# 知识实体类型（实体索引集合）
# ---------------------------
ENTITY_TYPE_COURSE = "course"           # 课程名（系列 / 课程）
ENTITY_TYPE_PROJECT = "project"         # 项目名
ENTITY_TYPE_QUESTION_BANK = "question_bank"  # 题库名

# ---------------------------
# 模型相关
# ---------------------------
BGE_DENSE_DIM = 1024

# 实体对齐阈值（与掌柜智库项目一致的评分口径）
ENTITY_CONFIRM_SCORE = 0.85
ENTITY_CANDIDATE_SCORE = 0.60

# 文档检索时默认使用的集合（用于过滤表达式）
DOC_CONTENT_TYPES = [CONTENT_TYPE_COURSE_DOC, CONTENT_TYPE_PROJECT_DOC]
