"""Bank relationship graph with local NetworkX scoring and Neo4j sync."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from math import floor
from typing import Any

import networkx as nx
from neo4j import AsyncGraphDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models_business import BankCard, DeviceFingerprint, LoginLog, Transaction
from app.models_risk import RiskLabel


@dataclass(frozen=True, slots=True)
class GraphEvaluation:
    score: int
    version: str
    backend: str
    signals: dict[str, Any]


class GraphRiskEngine:
    name = "bank-relationship-graph"
    version = "bank-graph-v1.1"

    def capabilities(self) -> list[str]:
        return [
            "shared-device",
            "shared-ip",
            "card-transfer-network",
            "fraud-neighbor-distance",
            "connected-community",
            "neo4j-sync",
        ]

    async def build_graph(self, session: AsyncSession) -> nx.Graph:
        graph = nx.Graph()
        devices = (await session.scalars(select(DeviceFingerprint))).all()
        logins = (await session.scalars(select(LoginLog))).all()
        cards = (await session.scalars(select(BankCard))).all()
        transactions = (await session.scalars(select(Transaction))).all()
        labels = (await session.scalars(select(RiskLabel))).all()
        fraud_users = {label.user_id for label in labels if label.label == "FRAUD"}

        def add_user(user_id: str) -> str:
            node = f"USER:{user_id}"
            graph.add_node(node, entity_type="USER", entity_id=user_id, fraud=user_id in fraud_users)
            return node

        for record in devices:
            user_node = add_user(record.user_id)
            device_node = f"DEVICE:{record.device_id}"
            graph.add_node(device_node, entity_type="DEVICE", entity_id=record.device_id)
            graph.add_edge(user_node, device_node, relation="USES_DEVICE")
        for login in logins:
            user_node = add_user(login.user_id)
            ip_node = f"IP:{login.ip}"
            graph.add_node(ip_node, entity_type="IP", entity_id=login.ip)
            graph.add_edge(user_node, ip_node, relation="LOGIN_FROM")
        for card in cards:
            user_node = add_user(card.user_id)
            card_node = f"CARD:{card.card_id}"
            graph.add_node(card_node, entity_type="CARD", entity_id=card.card_id)
            graph.add_edge(user_node, card_node, relation="OWNS_CARD")
        for transaction in transactions:
            user_node = add_user(transaction.user_id)
            if transaction.from_card:
                from_node = f"CARD:{transaction.from_card}"
                graph.add_node(from_node, entity_type="CARD", entity_id=transaction.from_card)
                graph.add_edge(user_node, from_node, relation="OPERATES_CARD")
            if transaction.from_card and transaction.to_card:
                to_node = f"CARD:{transaction.to_card}"
                graph.add_node(to_node, entity_type="CARD", entity_id=transaction.to_card)
                graph.add_edge(
                    f"CARD:{transaction.from_card}",
                    to_node,
                    relation="TRANSFER_TO",
                    txn_id=transaction.txn_id,
                    amount=float(transaction.amount),
                )
        return graph

    async def evaluate(
        self,
        user_id: str,
        features: dict[str, Any],
        session: AsyncSession,
    ) -> GraphEvaluation:
        graph = await self.build_graph(session)
        signals: dict[str, Any] = {}
        signal_scores: list[int] = []

        def add_signal(name: str, value: Any, score: int) -> None:
            signals[name] = {"value": value, "score": score}
            signal_scores.append(score)

        shared_device = int(features.get("device_user_count") or 0)
        if shared_device >= 5:
            add_signal("shared_device_users", shared_device, min(80, 40 + shared_device * 5))
        fan_in = int(features.get("distinct_from_cards_1h") or 0)
        if fan_in >= 3:
            add_signal("card_fan_in_1h", fan_in, min(95, 55 + fan_in * 10))
        if features.get("beneficiary_blacklisted"):
            add_signal("blacklisted_beneficiary", True, 100)
        if features.get("is_proxy") or features.get("is_tor"):
            add_signal("anonymous_network", True, 40)

        event_ip = features.get("ip")
        if event_ip and not self._is_private_ip(str(event_ip)):
            ip_node = f"IP:{event_ip}"
            if ip_node in graph:
                ip_users = sum(1 for node in graph.neighbors(ip_node) if node.startswith("USER:"))
                if ip_users >= 5:
                    add_signal("shared_public_ip_users", ip_users, min(70, 30 + ip_users * 5))

        root = f"USER:{user_id}"
        if root in graph:
            fraud_neighbors: list[dict[str, Any]] = []
            # Fraud risk is propagated only through a directly shared entity
            # (USER -> DEVICE/CARD -> USER).  A three-hop transfer-counterparty
            # path is common in normal banking traffic and created widespread
            # false positives in dense payment networks.
            paths = nx.single_source_shortest_path(graph, root, cutoff=2)
            for node, path in paths.items():
                if node == root or not node.startswith("USER:") or not graph.nodes[node].get("fraud"):
                    continue
                if len(path) == 3 and path[1].startswith(("DEVICE:", "CARD:")):
                    fraud_neighbors.append({"user_id": node.split(":", 1)[1], "distance": len(path) - 1})
            if fraud_neighbors:
                add_signal("fraud_neighbors", fraud_neighbors[:10], 75)

        if not signal_scores:
            score = 0
        else:
            ordered = sorted(signal_scores, reverse=True)
            raw_score = ordered[0] + sum(ordered[1:]) * 0.15
            score = min(100, floor(raw_score + 0.5))
        return GraphEvaluation(
            score=score,
            version=self.version,
            backend=settings.GRAPH_BACKEND,
            signals=signals,
        )

    async def neighborhood(self, user_id: str, session: AsyncSession, depth: int = 2) -> dict:
        graph = await self.build_graph(session)
        root = f"USER:{user_id}"
        if root not in graph:
            return {"user_id": user_id, "nodes": [], "edges": [], "community_size": 0}
        subgraph = graph.subgraph(nx.single_source_shortest_path_length(graph, root, cutoff=depth))
        nodes = [
            {"id": node, **attributes}
            for node, attributes in subgraph.nodes(data=True)
        ]
        edges = [
            {"source": source, "target": target, **attributes}
            for source, target, attributes in subgraph.edges(data=True)
        ]
        community_size = len(nx.node_connected_component(graph, root))
        return {
            "user_id": user_id,
            "nodes": nodes,
            "edges": edges,
            "community_size": community_size,
            "backend": settings.GRAPH_BACKEND,
        }

    async def sync_to_neo4j(self, session: AsyncSession) -> dict[str, int]:
        if not settings.NEO4J_PASSWORD:
            raise RuntimeError("NEO4J_PASSWORD 未配置")
        graph = await self.build_graph(session)
        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        try:
            async with driver.session(database=settings.NEO4J_DATABASE) as neo_session:
                await neo_session.run("MATCH (n:BankRiskEntity) DETACH DELETE n")
                await neo_session.run(
                    "UNWIND $nodes AS node MERGE (n:BankRiskEntity {id: node.id}) SET n += node.props",
                    nodes=[{"id": node, "props": attrs} for node, attrs in graph.nodes(data=True)],
                )
                await neo_session.run(
                    "UNWIND $edges AS edge MATCH (a:BankRiskEntity {id: edge.source}), (b:BankRiskEntity {id: edge.target}) MERGE (a)-[r:RELATED_TO {key: edge.key}]->(b) SET r += edge.props",
                    edges=[
                        {
                            "source": source,
                            "target": target,
                            "key": f"{source}|{target}",
                            "props": attrs,
                        }
                        for source, target, attrs in graph.edges(data=True)
                    ],
                )
        finally:
            await driver.close()
        return {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()}

    @staticmethod
    def _is_private_ip(value: str) -> bool:
        try:
            return ip_address(value).is_private
        except ValueError:
            return False


graph_engine = GraphRiskEngine()
