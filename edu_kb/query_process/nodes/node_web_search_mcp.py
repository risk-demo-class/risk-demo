# -*- coding: utf-8 -*-
import asyncio
import json

from agents.mcp import MCPServerStreamableHttp

from edu_kb.config.config import mcp_config
from edu_kb.query_process.base import NodeBase
from edu_kb.query_process.state import QueryGraphState
from edu_kb.tool.logger import logger


class NodeWebSearchMcp(NodeBase):
    """
    节点功能：调用外部搜索引擎补充信息（可选）
    未配置 MCP 时直接跳过，不影响主流程。
    """

    name = "node_web_search_mcp"

    def process(self, state: QueryGraphState):
        if not mcp_config.mcp_base_url:
            logger.warning("未配置 MCP_DASHSCOPE_BASE_URL，跳过网络搜索")
            return {"web_search_docs": []}

        try:
            query = state.get("rewritten_query") or state.get("original_query")
            result = asyncio.run(self._mcp_call(query))
            result_dict = json.loads(result.content[0].text)
            pages = result_dict.get("pages") or []
            docs = []
            for item in pages:
                docs.append({
                    "title": item.get("title") or "",
                    "snippet": item.get("snippet") or "",
                    "url": item.get("url") or "",
                })
            return {"web_search_docs": docs}
        except Exception as e:
            logger.exception(f"MCP调用失败:{e}")
            return {"web_search_docs": []}

    async def _mcp_call(self, query: str):
        async with MCPServerStreamableHttp(
            name="search_mcp",
            params={
                "url": mcp_config.mcp_base_url,
                "headers": {"Authorization": f"Bearer {mcp_config.api_key}"},
                "timeout": 30,
            },
            cache_tools_list=True,
            max_retry_attempts=3,
            client_session_timeout_seconds=30,
        ) as server:
            result = await server.call_tool(
                tool_name="bailian_web_search",
                arguments={"query": query, "count": 5},
            )
            return result
