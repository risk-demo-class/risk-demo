# 教育知识库（教育实战）

基于《尚硅谷大模型项目实战之掌柜智库》参考架构实现的**教育知识库实战项目**，面向教育培训场景，提供：

- **内容导入**：课程介绍、课程讲义（docx）、项目文档、题库与题目，导入过程支持任务状态追踪与教育元数据管理（课程名、项目名、章节名、题库名、来源文件名等）
- **课程检索与介绍**：按课程名、项目名、知识点检索，返回课程列表、课程详情、章节结构、适合人群与学习目标
- **文档检索**：定位课程文档 / 项目文档片段，返回课程名、项目名、章节名、文件名等来源信息
- **题库检索**：查询题目详情，返回题目内容、题型、选项、答案与解析
- **知识问答**：基于知识库内容流式生成答案，并返回结构化引用信息
- **交互能力**：单轮问答、多轮对话（历史记录管理）、SSE 流式输出

## 技术架构

与掌柜智库项目保持同构，将“商品实体”替换为“教育知识实体”，并进行教育场景增强：

| 层 | 模块 | 说明 |
| --- | --- | --- |
| 导入层 | `edu_kb/import_process` | LangGraph 工作流：docx/pdf/md → Markdown → 图片处理 → 课程/题库解析 或 文档切分 → 教育元数据识别 → BGE-M3 向量化 → Milvus 入库 → 知识实体索引 |
| 查询层 | `edu_kb/query_process` | LangGraph 工作流：意图分析 + 实体对齐 → 课程/文档/HyDE/题目/网络 多路检索 → RRF 融合 → Rerank 重排 → 流式答案生成 + 引用 |
| Web 层 | `edu_kb/web` | FastAPI 导入服务（8000）+ 查询服务（8001）+ 前端页面（导入页 / 对话页） |
| 存储层 | Milvus / MinIO / MongoDB | 向量检索、图片托管、多轮对话历史 |

## 目录结构

```text
教育实战/
├── edu_kb/                     # 主包
│   ├── config/                 # 配置与常量
│   ├── tool/                   # 日志
│   ├── utils/                  # LLM / 向量 / Milvus / MinIO / MongoDB / SSE / 任务追踪
│   │   ├── docx_utils.py       # docx -> Markdown（纯标准库，含标题/表格/图片/代码块）
│   │   ├── course_intro_parser.py  # 课程介绍解析
│   │   └── question_bank_parser.py # 题库解析
│   ├── import_process/         # 导入工作流（LangGraph）
│   ├── query_process/          # 查询工作流（LangGraph）
│   └── web/                    # FastAPI 服务 + 前端页面
├── data/
│   └── demo/                   # 开箱即用的演示数据
├── scripts/
│   ├── import_education_data.py # 一键导入教育数据
│   └── seed_demo_data.py        # 重置演示数据
├── tests/                       # 解析器单元测试（纯标准库）
└── docs/                        # 需求对照、架构、部署指南
```

## 快速开始

### 1. 准备环境

```bash
# 创建虚拟环境并安装依赖（Python >= 3.11）
uv sync
# 或
python -m venv .venv
.venv\Scripts\activate
pip install -r <由 pyproject.toml 生成的依赖>
```

复制 `.env.example` 为 `.env`，填写：

- `OPENAI_API_KEY` / `OPENAI_BASE_URL`（DashScope 兼容模式）
- `MILVUS_URL`（向量数据库）
- `MONGO_URL`（对话历史）
- `MINIO_*`（图片托管，可选）
- `DATA_BASED_ROOT_DIR`（上传文件落地目录，可选）

### 2. 导入教育数据

方式一：直接调用导入工作流（无需启动服务）

```bash
python scripts/import_education_data.py
```

脚本会自动定位真实的《教育》数据目录（`尚硅谷大模型项目实战之掌柜智库实战\资料\教育\数据`）；
也可以指定演示数据：

```bash
python scripts/import_education_data.py --data-root data/demo
```

方式二：启动导入服务后通过页面 / HTTP 上传

```bash
uvicorn edu_kb.web.api.import_service:app --host 0.0.0.0 --port 8000
# 打开 http://127.0.0.1:8000/import.html
```

导入建议顺序：先导入 `课程介绍.md` 与 `题目资料.md`，再导入 `课程文档/*.docx` 与 `项目文档/*.docx`。

### 3. 启动智能问答

```bash
uvicorn edu_kb.web.api.query_service:app --host 0.0.0.0 --port 8001
# 打开 http://127.0.0.1:8001/chat.html
```

### 4. 体验示例问题

- 有哪些 Python 相关的课程？
- 推荐一个适合入门的 RAG 课程
- Python 有哪些练习题？
- 查询函数相关的选择题
- 什么是协程？FastAPI 里怎么用？

## 数据模型

Milvus 中创建四个教育知识库专用集合：

| 集合 | 用途 | 核心字段 |
| --- | --- | --- |
| `edu_courses` | 课程介绍 | course_name / series_name / category / suitable_for / goals / class_hours / period / description |
| `edu_chunks` | 文档切片 | content / content_type / course_name / project_name / chapter_name / file_title / source_path |
| `edu_questions` | 题库题目 | question_code / bank_name / question_type / question_text / options / answer / analysis |
| `edu_entities` | 知识实体索引 | entity_name / entity_type（course / project / question_bank） |

详细说明见 [docs/架构与数据模型.md](docs/架构与数据模型.md)。

## 测试

```bash
python tests/test_parsers.py
```

覆盖课程介绍解析、题库解析、文本切分兜底、真实教育数据（657 门课程 / 1752 道题）验证。

## 文档

- [需求实现对照](docs/需求实现对照.md)
- [架构与数据模型](docs/架构与数据模型.md)
- [部署指南](docs/部署指南.md)
