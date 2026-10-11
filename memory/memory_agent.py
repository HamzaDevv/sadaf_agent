"""
memory/memory_agent.py — Sadaf V6 Spreading Activation Memory Traversal

1. Seed Activation: vector similarity (ChromaDB) + keyword matching.
2. Graph Spreading: heuristic energy spread to neighbors.
3. LLM Top-K Pruning: ask LLM which of the top activated nodes are truly relevant.
"""

import json
from collections import deque
from typing import Optional, Union, Any
from memory.graph_store import MemoryGraphStore
from memory.schemas import MemoryNode
from config import SUBAGENT_MODEL, PRIORITY_AGENT
from llm_proxy import llm_proxy

TRAVERSAL_PROMPT = """\
You are a cognitive memory graph traversal agent.
We have found some highly activated memory nodes based on the user's query and
spreading activation through their memory graph.

USER QUERY: {query}

TOP ACTIVATED SUBGRAPH:
{subgraph}

Your job is to prune this context. Output ONLY a JSON array of the node IDs
that are highly relevant to answering the user's query. If none are relevant, output [].
Example: ["career:company", "identity:name"]
"""

class MemoryAgent:
    """LLM-Guided Spreading Activation Traversal."""

    def __init__(self, graph_store: MemoryGraphStore):
        self.store = graph_store

    async def retrieve_context(
        self,
        user_id: str,
        user_query: str = "",
        buffer: Optional[Any] = None,
    ) -> str:
        """Retrieves memory context for the given user and query."""
        if buffer is None:
            buffer = []
        return await self.build_context(user_id=user_id, buffer=buffer, user_query=user_query)

    async def build_context(
        self,
        user_id: str,
        buffer: Union[deque, list],
        user_query: str = "",
    ) -> str:
        self.store.ensure_user_dir(user_id)

        # 1. Recent sessions
        recent_sessions = self.store.get_last_n_sessions(user_id, n=5)

        # 2. Identity Context
        all_nodes_dict = self.store.get_all_nodes(user_id)
        identity_nodes = {nid: n for nid, n in all_nodes_dict.items() if n.get("section") == "identity"}

        identity_context = "Identity Context:\n"
        if identity_nodes:
            identity_context += "\n".join([f"- {n['key']}: {n['value']}" for n in identity_nodes.values()])
        else:
            identity_context += "- None"

        # 3. Spreading Activation + LLM Pruning
        traversed_context = await self._spreading_activation(user_id, user_query, all_nodes_dict)

        # 4. Short-term buffer
        recent_turns = list(buffer)[-5:] if buffer is not None else []
        buffer_context = ""
        if recent_turns:
            formatted_lines = []
            for item in recent_turns:
                if isinstance(item, (tuple, list)) and len(item) == 2:
                    formatted_lines.append(f"You: {item[0]}\nSadaf: {item[1]}")
                else:
                    formatted_lines.append(str(item))
            lines_str = "\n".join(formatted_lines)
            buffer_context = f"# This Conversation (last {len(recent_turns)} turns)\n{lines_str}"

        # Assemble
        sections = [identity_context, traversed_context, recent_sessions, buffer_context]
        return "\n\n".join([s for s in sections if s.strip()]).strip()

    async def _spreading_activation(self, user_id: str, query: str, all_nodes: dict) -> str:
        if not query or not all_nodes:
            return ""

        # Reciprocal Rank Fusion (RRF) lists
        # List 1: Vector Search Ranks
        vector_seeds = self.store.vector_search(user_id, query, top_k=15)

        # List 2: Keyword Match Ranks
        keyword_seeds = []
        query_words = set(query.lower().split())
        for nid, n in all_nodes.items():
            content = f"{n.get('section', '')} {n.get('key', '')} {n.get('value', '')}".lower()
            overlap = sum(1 for w in query_words if len(w) > 3 and w in content)
            if overlap > 0:
                keyword_seeds.append((nid, overlap))
        keyword_seeds.sort(key=lambda x: x[1], reverse=True)
        keyword_rank_ids = [k[0] for k in keyword_seeds]

        # List 3: Graph Spreading Activation
        initial_seeds = set(vector_seeds[:5] + keyword_rank_ids[:5])
        activation = {nid: 0.0 for nid in all_nodes.keys()}
        for seed in initial_seeds:
            if seed in all_nodes:
                activation[seed] = 10.0 * all_nodes[seed].get("stability", 1.0)

        data = self.store._load_json(self.store._graph_path(user_id), {"edges": []})
        edges = data.get("edges", [])
        adjacency = {}
        for edge in edges:
            fn, tn, w = edge["from_node"], edge["to_node"], edge.get("weight", 1.0)
            if fn not in adjacency: adjacency[fn] = []
            if tn not in adjacency: adjacency[tn] = []
            adjacency[fn].append((tn, w))
            adjacency[tn].append((fn, w))

        for seed in initial_seeds:
            if seed in adjacency and seed in all_nodes:
                for neighbor, weight in adjacency[seed]:
                    if neighbor in all_nodes:
                        n_stab = all_nodes[neighbor].get("stability", 1.0)
                        activation[neighbor] += (activation[seed] * 0.5) * weight * n_stab

        sorted_spread = sorted(activation.items(), key=lambda x: x[1], reverse=True)
        spread_rank_ids = [s[0] for s in sorted_spread if s[1] > 0.0]

        # Combine with RRF: score(d) = sum(1 / (k + rank))
        rrf_k = 60
        rrf_scores = {}
        for rank_list in [vector_seeds, keyword_rank_ids, spread_rank_ids]:
            for rank, nid in enumerate(rank_list):
                if nid in all_nodes:
                    rrf_scores[nid] = rrf_scores.get(nid, 0.0) + (1.0 / (rrf_k + rank + 1))

        if not rrf_scores:
            return ""

        sorted_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        # Adjust capacity: for high-context models, retrieve top 35 nodes; otherwise top 15
        from config import AI_PROVIDER
        max_subgraph_size = 35 if AI_PROVIDER in ("deepseek", "gemini") else 15
        top_k = [nid for nid, _ in sorted_rrf[:max_subgraph_size]]

        subgraph = self.store.get_subgraph(user_id, top_k)

        # Step 4: LLM Final Pruning (only if subgraph exceeds high threshold)
        if len(top_k) <= 25:
            print(f"[MemoryAgent] Utilizing full RRF subgraph ({len(top_k)} nodes active)")
            final_nodes = top_k
        else:
            subgraph_str = json.dumps(subgraph, indent=2)
            prompt = TRAVERSAL_PROMPT.format(query=query, subgraph=subgraph_str)
            final_nodes = top_k
            try:
                raw = await llm_proxy.call(
                    model=SUBAGENT_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    priority=PRIORITY_AGENT,
                    temperature=0.0,
                    max_tokens=250,
                )
                if raw:
                    try:
                        start = raw.index("[")
                        end = raw.rindex("]") + 1
                        match = raw[start:end]
                        llm_picked = json.loads(match)
                        if isinstance(llm_picked, list):
                            final_nodes = [n for n in llm_picked if n in all_nodes]
                    except ValueError:
                        pass
            except Exception as e:
                print(f"[MemoryAgent] LLM pruning failed: {e}")

        # Assemble final context
        if not final_nodes:
            return ""

        final_subgraph = self.store.get_subgraph(user_id, final_nodes)

        context = "Relevant Memory Subgraph:\n"
        for nid, n in final_subgraph["nodes"].items():
            key = n.get('key', nid)
            val = n.get('value', '')
            conf = n.get('confidence', 1.0)
            context += f"- {key}: {val} (confidence: {conf:.2f})\n"

        if final_subgraph["edges"]:
            context += "Relationships:\n"
            for edge in final_subgraph["edges"]:
                context += f"- {edge['from_node']} [{edge['relation']}] -> {edge['to_node']}\n"

        return context
