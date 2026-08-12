# -*- coding: utf-8 -*-
"""
解析器单元测试（纯标准库，无需外部依赖）
运行：python tests/test_parsers.py
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from edu_kb.utils.course_intro_parser import parse_course_intro, build_course_search_text
from edu_kb.utils.question_bank_parser import parse_question_bank, build_question_search_text
from edu_kb.utils.text_utils import split_text_by_size, strip_filename_version, dedupe_preserve_order


COURSE_INTRO_SAMPLE = """# 课程
共 1 个课程系列

## Python 基础班
- **系列编码**: python_foundation
- **描述**: 编程入门系列
- **课程分类**: 计算机 / 编程语言
- **适合人群**: 在校生
- **学习目标**: 技能提升
- **适合年级**: 专科

### 课程
- **Python 语法入门**
  - 编码: python_foundation_m1, 课时: 8, 学时: 16.00
  - 描述: 语法与开发环境
- **函数与数据结构**
  - 编码: python_foundation_m2, 课时: 10, 学时: 20.00
  - 描述: 函数抽象与常用数据结构
"""


QUESTION_BANK_SAMPLE = """# 题目
共 1 个题库，3 个题目

## Python 题库
- 题库编码: python_bank

### python_bank_q001
- **题型**: 单选题
- **题干**: Python 中哪个关键字用于定义函数？
- **选项**:
A. def
B. function
C. func
D. lambda
- **答案**: A
- **解析**: def 是 Python 定义函数的关键字。

### python_bank_q002
- **题型**: 编程题
- **题干**: 编写函数计算列表元素之和。

```python
def sum_list(nums):
    pass
```
- **答案**: 遍历列表并累加。
- **解析**: 考查循环与累加。

### python_bank_q003
- **题型**: 判断题
- **题干**: 列表下标从 0 开始。对还是错？
- **选项**:
A. 对
B. 错
- **答案**: 对
- **解析**: 常见语言均从 0 开始。
"""


def test_course_intro_parser():
    records = parse_course_intro(COURSE_INTRO_SAMPLE, "课程介绍.md")
    assert len(records) == 2, f"期望2门课程，实际{len(records)}"
    first = records[0]
    assert first["course_name"] == "Python 语法入门"
    assert first["course_code"] == "python_foundation_m1"
    assert first["class_hours"] == "8"
    assert first["period"] == "16.00"
    assert first["series_name"] == "Python 基础班"
    assert first["series_code"] == "python_foundation"
    assert build_course_search_text(first)
    print("✓ 课程介绍解析测试通过")


def test_question_bank_parser():
    questions = parse_question_bank(QUESTION_BANK_SAMPLE, "题目资料.md")
    assert len(questions) == 3, f"期望3道题，实际{len(questions)}"
    single = questions[0]
    assert single["question_type"] == "单选题"
    assert single["options"] == ["A. def", "B. function", "C. func", "D. lambda"]
    assert single["answer"] == "A"
    assert single["analysis"]

    code_q = questions[1]
    assert code_q["question_type"] == "编程题"
    assert "```python" in code_q["question_text"], "编程题题干应保留代码块"
    assert code_q["options"] == []

    judge = questions[2]
    assert judge["question_type"] == "判断题"
    assert judge["answer"] == "对"
    assert build_question_search_text(single)
    print("✓ 题库解析测试通过")


def test_text_utils():
    long_text = "第一段。" * 500
    chunks = split_text_by_size(long_text, max_length=300, overlap=50)
    assert len(chunks) >= 2
    assert all(len(c) <= 330 for c in chunks)
    assert strip_filename_version("尚硅谷大模型技术之Python1.0.docx") == "Python"
    assert strip_filename_version("尚硅谷大模型技术之智图寻宝2.0.0.docx") == "智图寻宝"
    assert dedupe_preserve_order(["a", "b", "a"]) == ["a", "b"]
    print("✓ 文本工具测试通过")


def test_real_data():
    """使用真实教育数据验证（文件存在时执行）"""
    real_root = Path(
        r"D:\SGGLearning\14.尚硅谷大模型项目之掌柜智库\尚硅谷大模型项目实战之掌柜智库实战\资料\教育\数据"
    )
    if not real_root.exists():
        print("（真实数据目录不存在，跳过真实数据测试）")
        return

    intro_file = real_root / "课程介绍.md"
    if intro_file.exists():
        records = parse_course_intro(intro_file.read_text(encoding="utf-8"), "课程介绍.md")
        assert len(records) >= 600, f"期望至少600门课程，实际{len(records)}"
        assert all(r["course_code"] for r in records[:10])
        print(f"✓ 真实课程介绍解析通过（{len(records)} 门课程）")

    bank_file = real_root / "题目资料.md"
    if bank_file.exists():
        questions = parse_question_bank(bank_file.read_text(encoding="utf-8"), "题目资料.md")
        assert len(questions) == 1752, f"期望1752道题，实际{len(questions)}"
        print(f"✓ 真实题库解析通过（{len(questions)} 道题）")


if __name__ == "__main__":
    test_course_intro_parser()
    test_question_bank_parser()
    test_text_utils()
    test_real_data()
    print("\n全部测试通过 ✅")
