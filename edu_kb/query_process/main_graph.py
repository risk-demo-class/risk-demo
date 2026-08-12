# -*- coding: utf-8 -*-
from typing import Optional, List

from langgraph.constants import END
from langgraph.graph import StateGraph

from edu_kb.config.constants import (
    INTENT_COURSE_DETAIL,
    INTENT_COURSE_INTRO,
    INTENT_QUESTION,
)
from edu_kb.query_process.nodes.node_answer_output import NodeAnswerOutput
from edu_kb.query_process.nodes.node_query_analyze import NodeQueryAnalyze
from edu_kb.query_process.nodes.node_rerank import NodeRerank
from edu_kb.query_process.nodes.node_rrf import NodeRrf
from edu_kb.query_process.nodes.node_search_course import NodeSearchCourse
from edu_kb.query_process.nodes.node_search_docs import NodeSearchDocs
from edu_kb.query_process.nodes.node_search_docs_hyde import NodeSearchDocsHyde
from edu_kb.query_process.nodes.node_search_questions import NodeSearchQuestions
from edu_kb.query_process.nodes.node_web_search_mcp import NodeWebSearchMcp
from edu_kb.query_process.state import QueryGraphState
from edu_kb.tool.logger import logger


class KBQueryWorkflow:
    """
    教育知识库查询工作流

    流程：
      node_query_analyze
        -> [有澄清答案] node_answer_output -> END
        -> [多路检索] node_search_course / node_search_docs / node_search_docs_hyde
                     / node_search_questions / node_web_search_mcp
        -> node_join -> node_rrf -> node_rerank -> node_answer_output -> END
    """

    def __init__(self):
        self.workflow = StateGraph(QueryGraphState)
        self._init_nodes()
        self._register_nodes()
        self._setup_routes()
        self._compiled_app: Optional[object] = None

    def _init_nodes(self):
        self.node_query_analyze = NodeQueryAnalyze()
        self.node_search_course = NodeSearchCourse()
        self.node_search_docs = NodeSearchDocs()
        self.node_search_docs_hyde = NodeSearchDocsHyde()
        self.node_search_questions = NodeSearchQuestions()
        self.node_web_search_mcp = NodeWebSearchMcp()
        self.node_rrf = NodeRrf()
        self.node_rerank = NodeRerank()
        self.node_answer_output = NodeAnswerOutput()

    def _register_nodes(self):
        self.workflow.add_node("node_query_analyze", self.node_query_analyze)
        self.workflow.add_node("node_multi_search", lambda x: x)
        self.workflow.add_node("node_search_course", self.node_search_course)
        self.workflow.add_node("node_search_docs", self.node_search_docs)
        self.workflow.add_node("node_search_docs_hyde", self.node_search_docs_hyde)
        self.workflow.add_node("node_search_questions", self.node_search_questions)
        self.workflow.add_node("node_web_search_mcp", self.node_web_search_mcp)
        self.workflow.add_node("node_join", lambda x: {})
        self.workflow.add_node("node_rrf", self.node_rrf)
        self.workflow.add_node("node_rerank", self.node_rerank)
        self.workflow.add_node("node_answer_output", self.node_answer_output)

    def _route_after_analyze(self, state: QueryGraphState):
        """意图分析后的条件路由：有澄清答案直接出答案，否则多路检索"""
        if state.get("answer"):
            return "node_answer_output"

        next_nodes: List[str] = [
            "node_search_docs",
            "node_search_docs_hyde",
            "node_web_search_mcp",
        ]
        intent = state.get("intent")
        if intent in (INTENT_COURSE_INTRO, INTENT_COURSE_DETAIL):
            next_nodes.insert(0, "node_search_course")
        if intent == INTENT_QUESTION:
            next_nodes.append("node_search_questions")
        return next_nodes

    def _setup_routes(self):
        self.workflow.set_entry_point("node_query_analyze")
        self.workflow.add_conditional_edges(
            "node_query_analyze",
            self._route_after_analyze,
            {
                "node_answer_output": "node_answer_output",
                "node_search_course": "node_search_course",
                "node_search_docs": "node_search_docs",
                "node_search_docs_hyde": "node_search_docs_hyde",
                "node_search_questions": "node_search_questions",
                "node_web_search_mcp": "node_web_search_mcp",
            },
        )

        # 多路检索并发执行
        self.workflow.add_edge("node_search_course", "node_join")
        self.workflow.add_edge("node_search_docs", "node_join")
        self.workflow.add_edge("node_search_docs_hyde", "node_join")
        self.workflow.add_edge("node_search_questions", "node_join")
        self.workflow.add_edge("node_web_search_mcp", "node_join")

        # 合并 -> 融合 -> 重排 -> 生成 -> 结束
        self.workflow.add_edge("node_join", "node_rrf")
        self.workflow.add_edge("node_rrf", "node_rerank")
        self.workflow.add_edge("node_rerank", "node_answer_output")
        self.workflow.add_edge("node_answer_output", END)

    def compile(self):
        if not self._compiled_app:
            self._compiled_app = self.workflow.compile()
        return self._compiled_app

    def run(self, initial_state: QueryGraphState, stream: bool = False):
        if not self._compiled_app:
            self.compile()
        if stream:
            return self._compiled_app.stream(initial_state)
        return self._compiled_app.invoke(initial_state)

    @classmethod
    def create_and_run(cls, init_state: QueryGraphState, stream: bool = False):
        workflow = cls()
        return workflow.run(init_state, stream)


if __name__ == "__main__":
    init_state = {
        "original_query": "有哪些 Python 相关的课程？",
        "session_id": "test_001",
        "task_id": "task_demo",
    }
    for chunk in KBQueryWorkflow.create_and_run(init_state, stream=True):
        logger.warning(chunk)
