# -*- coding: utf-8 -*-

IMAGE_SUMMARY = """这是"{file_title}"文件中的一张图片，图片上文部分为"{context[0]}"，
下文部分为"{context[1]}"，请用中文简要总结这张图片的内容，用于 Markdown 图片标题。"""


EDU_METADATA_RECOGNITION = """你是教育知识库的元数据识别专家。请根据以下信息，识别这份教育资料对应的课程元数据。

文件名：{file_title}
内容类型：{content_type_cn}

正文切片（用于辅助识别）：
{context}

要求：
1. course_name：这份资料对应的课程名称。例如文件名"尚硅谷大模型技术之Python1.0"对应课程名"Python"。
2. project_name：如果这是项目实战资料，返回项目名称；否则返回空字符串。
3. chapter_names：从正文切片中识别出的章节名称列表（最多 8 个）。
4. knowledge_points：从正文切片中识别出的核心知识点列表（最多 8 个）。

请直接返回 JSON 格式结果，不要添加任何解释：
{{
    "course_name": "",
    "project_name": "",
    "chapter_names": [],
    "knowledge_points": []
}}
"""
