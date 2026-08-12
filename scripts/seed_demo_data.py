# -*- coding: utf-8 -*-
"""
生成 / 重置教育知识库演示数据（data/demo）
演示数据包含：课程介绍、题库、课程讲义、项目文档
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = PROJECT_ROOT / "data" / "demo"


DEMO_FILES = {
    "课程介绍.md": """# 课程（演示数据）\n共 3 个课程系列\n\n## 通用编程入门班\n- **系列编码**: general_purpose_programming_foundation\n- **描述**: 计算机科学能力线 / 通用程序设计 / 通用编程入门班\n- **课程分类**: 计算机 / 编程语言 / 通用程序设计\n- **适合人群**: 在校生, 职场人, 求职者\n- **学习目标**: 技能提升, 求职上岸, 转岗转行\n- **适合年级**: 专科, 本科\n\n### 课程\n- **语法基础与开发环境**\n  - 编码: general_purpose_programming_foundation_m1, 课时: 8, 学时: 16.00\n  - 描述: 通用程序设计 / 项目实践 / 工程能力\n- **流程控制与数据结构入门**\n  - 编码: general_purpose_programming_foundation_m2, 课时: 10, 学时: 20.00\n  - 描述: 通用程序设计 / 项目实践 / 工程能力\n\n## 大模型应用开发班\n- **系列编码**: llm_application_development\n- **描述**: 大模型应用线 / RAG 与智能体 / 大模型应用开发班\n- **课程分类**: 计算机 / 数据与人工智能 / 大模型应用\n- **适合人群**: 在校生, 职场人, 求职者\n- **学习目标**: 技能提升, 求职上岸, 转岗转行\n- **适合年级**: 本科, 硕士研究生\n\n### 课程\n- **提示工程与 RAG 基础**\n  - 编码: llm_application_development_m1, 课时: 12, 学时: 24.00\n  - 描述: 提示工程 / RAG 检索增强生成 / 向量数据库入门\n- **应用 Demo 搭建与部署**\n  - 编码: llm_application_development_m3, 课时: 10, 学时: 20.00\n  - 描述: 流式输出 / SSE / 前后端联调 / 生产部署\n""",
    "题目资料.md": """# 题目（演示数据）\n共 1 个题库，2 个题目\n\n## 通用程序设计题库\n- 题库编码: general_purpose_programming_bank\n\n### general_purpose_programming_bank_q001\n- **题型**: 单选题\n- **题干**: 关于变量与常量的说法，哪一项更符合常见程序设计实践？\n- **选项**:\nA. 变量一旦赋值就不能再改变\nB. 常量用于表示运行过程中不应被修改的值\nC. 常量和变量没有任何区别\nD. 变量只能保存整数\n- **答案**: B\n- **解析**: 常量用于表达业务中不希望被修改的值，能提升代码可读性和安全性。\n\n### general_purpose_programming_bank_q002\n- **题型**: 编程题\n- **题干**: 编写一个函数 `count_vowels(text)`，统计字符串中元音字母 `a, e, i, o, u` 的出现次数，忽略大小写。\n- **答案**: 可先统一转为小写，再遍历统计字符是否属于元音集合，返回计数结果。\n- **解析**: 考查字符串遍历、集合判断和基本函数设计。\n""",
    "课程文档/尚硅谷大模型技术之Python1.0.md": "# Python 程序设计（演示讲义）\n\n## 课程定位\n\n本课程面向零基础学员，系统讲解 Python 基础语法、流程控制、函数与常用数据结构。\n\n## 变量与数据类型\n\nPython 中的变量不需要显式声明类型，赋值即创建。\n常见数据类型包括整数、浮点数、字符串、布尔值、列表、元组、字典与集合。\n\n```python\nname = \"张三\"\nage = 18\n```\n\n## 流程控制\n\n`for` 循环适合遍历可迭代对象，`while` 循环适合条件重复执行。\n\n```python\ntotal = 0\nfor i in range(1, 101):\n    total += i\nprint(total)\n```\n\n## 函数\n\n函数用于封装可复用的逻辑。\n\n```python\ndef add(a, b):\n    return a + b\n```\n",
    "项目文档/尚硅谷大模型技术之智能问答项目1.0.md": "# 智能问答项目实战（演示项目文档）\n\n## 项目背景\n\n本项目基于 RAG（检索增强生成）架构，搭建面向教育培训场景的智能问答系统。\n\n## 系统架构\n\n项目分为导入层、查询层、Web 层与存储层。\n\n| 层级 | 说明 |\n| --- | --- |\n| 导入层 | 文档解析、切分、向量化、入库 |\n| 查询层 | 意图识别、多路检索、融合重排 |\n| Web 层 | 上传、问答、流式输出 |\n| 存储层 | Milvus、MinIO、MongoDB |\n\n## 查询流程\n\n1. 分析用户意图。\n2. 对齐课程 / 项目 / 题库实体。\n3. 多路检索并融合重排。\n4. 流式生成答案并返回引用信息。\n",
}


def main():
    for rel_path, content in DEMO_FILES.items():
        target = DEMO_DIR / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"已生成：{target.relative_to(PROJECT_ROOT)}")
    print("\n演示数据生成完成，可使用 scripts/import_education_data.py --data-root data/demo 导入。")


if __name__ == "__main__":
    main()
