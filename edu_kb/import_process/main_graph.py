# -*- coding: utf-8 -*-
from typing import Optional

from langgraph.constants import END
from langgraph.graph import StateGraph

from edu_kb.config.constants import (
    CONTENT_TYPE_COURSE_INTRO,
    CONTENT_TYPE_QUESTION,
)
from edu_kb.import_process.nodes.node_bge_embedding import NodeBGEEmbedding
from edu_kb.import_process.nodes.node_course_intro_import import NodeCourseIntroImport
from edu_kb.import_process.nodes.node_doc_to_md import NodeDocToMD
from edu_kb.import_process.nodes.node_document_split import NodeDocumentSplit
from edu_kb.import_process.nodes.node_entry import NodeEntry
from edu_kb.import_process.nodes.node_import_entity_index import NodeImportEntityIndex
from edu_kb.import_process.nodes.node_import_milvus import NodeImportMilvus
from edu_kb.import_process.nodes.node_md_img import NodeMDImg
from edu_kb.import_process.nodes.node_metadata_recognition import NodeMetadataRecognition
from edu_kb.import_process.nodes.node_question_bank_import import NodeQuestionBankImport
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger


class KBImportWorkflow:
    """
    教育知识库导入工作流

    流程：
      node_entry -> node_doc_to_md -> node_md_img
         -> [课程介绍] node_course_intro_import -> node_import_entity_index -> END
         -> [题库]    node_question_bank_import -> node_import_entity_index -> END
         -> [文档]    node_document_split -> node_metadata_recognition
                     -> node_bge_embedding -> node_import_milvus
                     -> node_import_entity_index -> END
    """

    def __init__(self):
        self.workflow = StateGraph(ImportGraphState)
        self._init_nodes()
        self._register_nodes()
        self._setup_routes()
        self._compiled_app: Optional[object] = None

    def _init_nodes(self):
        self.node_entry = NodeEntry()
        self.node_doc_to_md = NodeDocToMD()
        self.node_md_img = NodeMDImg()
        self.node_course_intro_import = NodeCourseIntroImport()
        self.node_question_bank_import = NodeQuestionBankImport()
        self.node_document_split = NodeDocumentSplit()
        self.node_metadata_recognition = NodeMetadataRecognition()
        self.node_bge_embedding = NodeBGEEmbedding()
        self.node_import_milvus = NodeImportMilvus()
        self.node_import_entity_index = NodeImportEntityIndex()

    def _register_nodes(self):
        self.workflow.add_node("node_entry", self.node_entry)
        self.workflow.add_node("node_doc_to_md", self.node_doc_to_md)
        self.workflow.add_node("node_md_img", self.node_md_img)
        self.workflow.add_node("node_course_intro_import", self.node_course_intro_import)
        self.workflow.add_node("node_question_bank_import", self.node_question_bank_import)
        self.workflow.add_node("node_document_split", self.node_document_split)
        self.workflow.add_node("node_metadata_recognition", self.node_metadata_recognition)
        self.workflow.add_node("node_bge_embedding", self.node_bge_embedding)
        self.workflow.add_node("node_import_milvus", self.node_import_milvus)
        self.workflow.add_node("node_import_entity_index", self.node_import_entity_index)

    def _route_after_md_img(self, state: ImportGraphState) -> str:
        """图片处理完成后，根据内容类型路由"""
        content_type = state.get("content_type")
        if content_type == CONTENT_TYPE_COURSE_INTRO:
            return "node_course_intro_import"
        if content_type == CONTENT_TYPE_QUESTION:
            return "node_question_bank_import"
        return "node_document_split"

    def _setup_routes(self):
        self.workflow.set_entry_point("node_entry")
        self.workflow.add_edge("node_entry", "node_doc_to_md")
        self.workflow.add_edge("node_doc_to_md", "node_md_img")
        self.workflow.add_conditional_edges(
            "node_md_img",
            self._route_after_md_img,
            {
                "node_course_intro_import": "node_course_intro_import",
                "node_question_bank_import": "node_question_bank_import",
                "node_document_split": "node_document_split",
            },
        )

        # 课程介绍 / 题库路径
        self.workflow.add_edge("node_course_intro_import", "node_import_entity_index")
        self.workflow.add_edge("node_question_bank_import", "node_import_entity_index")

        # 文档路径
        self.workflow.add_edge("node_document_split", "node_metadata_recognition")
        self.workflow.add_edge("node_metadata_recognition", "node_bge_embedding")
        self.workflow.add_edge("node_bge_embedding", "node_import_milvus")
        self.workflow.add_edge("node_import_milvus", "node_import_entity_index")
        self.workflow.add_edge("node_import_entity_index", END)

    def compile(self):
        if not self._compiled_app:
            self._compiled_app = self.workflow.compile()
        return self._compiled_app

    def run(self, init_state: ImportGraphState, stream: bool = False):
        if not self._compiled_app:
            self.compile()
        if stream:
            return self._compiled_app.stream(init_state)
        return self._compiled_app.invoke(init_state)

    @classmethod
    def create_and_run(cls, init_state: ImportGraphState, stream: bool = False):
        workflow = cls()
        return workflow.run(init_state, stream)


if __name__ == "__main__":
    init_state = {
        "task_id": "task_demo",
        "local_file_path": r"D:\demo\课程介绍.md",
        "local_dir": r"D:\demo\output",
    }
    for chunk in KBImportWorkflow.create_and_run(init_state, stream=True):
        logger.info(chunk.keys())
        logger.info(chunk.items())
