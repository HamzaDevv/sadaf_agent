"""
memory/memory_agent.py — Sadaf V6 Spreading Activation Memory Traversal

1. Seed Activation: vector similarity (ChromaDB) + keyword matching.
2. Graph Spreading: heuristic energy spread to neighbors.
3. LLM Top-K Pruning: ask LLM which of the top activated nodes are truly relevant.
"""

import json
from collections import deque
from memory.graph_store import MemoryGraphStore
from memory.schemas import MemoryNode
from config import CHAT_MODEL, PRIORITY_AGENT
from groq_proxy import groq_proxy

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

    async def build_context(
        self,
        user_id: str,
        buffer: deque,
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
        recent_turns = list(buffer)[-5:]
        buffer_context = ""
        if recent_turns:
            lines = "\n".join(f"You: {u}\nSadaf: {a}" for u, a in recent_turns)
            buffer_context = f"# This Conversation (last {len(recent_turns)} turns)\n{lines}"

        # Assemble
        sections = [identity_context, traversed_context, recent_sessions, buffer_context]
        return "\n\n".join([s for s in sections if s.strip()]).strip()

    async def _spreading_activation(self, user_id: str, query: str, all_nodes: dict) -> str:
        if not query:
            return ""

        # Step 1: Seed Activation
        seeds = set()
        
        # Keyword matches
        query_words = set(query.lower().split())
        for nid, n in all_nodes.items():
            content = f"{n.get('section', '')} {n.get('key', '')} {n.get('value', '')}".lower()
            if any(word in content for word in query_words if len(word) > 3):
                seeds.add(nid)
                
        # Vector search
        vector_seeds = self.store.vector_search(user_id, query, top_k=5)
        for vs in vector_seeds:
            if vs in all_nodes:
                seeds.add(vs)
                
        if not seeds:
            return ""

        # Step 2: Graph Spreading Heuristic
        # Fetch edges
        data = self.store._load_json(self.store._graph_path(user_id), {"edges": []})
        edges = data.get("edges", [])
        
        adjacency = {}
        for edge in edges:
            fn = edge["from_node"]
            tn = edge["to_node"]
            w = edge.get("weight", 1.0)
            if fn not in adjacency: adjacency[fn] = []
            if tn not in adjacency: adjacency[tn] = []
            adjacency[fn].append((tn, w))
            adjacency[tn].append((fn, w)) # Assume undirected for spread

        activation = {nid: 0.0 for nid in all_nodes.keys()}
        
        # Initial energy for seeds
        for seed in seeds:
            node_stab = all_nodes[seed].get("stability", 1.0)
            activation[seed] = 10.0 * node_stab

        # Spread 1 hop
        for seed in seeds:
            if seed in adjacency:
                for neighbor, weight in adjacency[seed]:
                    if neighbor in all_nodes:
                        n_stab = all_nodes[neighbor].get("stability", 1.0)
                        spread_energy = (activation[seed] * 0.5) * weight * n_stab
                        activation[neighbor] += spread_energy

        # Step 3: Top-K Pruning (Heuristic)
        # Sort by activation
        sorted_nodes = sorted(activation.items(), key=lambda x: x[1], reverse=True)
        top_k = [nid for nid, energy in sorted_nodes if energy > 0.0][:10] # Top 10

        if not top_k:
            return ""

        subgraph = self.store.get_subgraph(user_id, top_k)

        # Step 4: LLM Final Pruning
        subgraph_str = json.dumps(subgraph, indent=2)
        prompt = TRAVERSAL_PROMPT.format(query=query, subgraph=subgraph_str)
        
        final_nodes = top_k
        try:
            raw = await groq_proxy.call(
                model=CHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                priority=PRIORITY_AGENT,
                temperature=0.0,
                max_tokens=150,
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
            context += f"- {nid} ({n['value']})\n"
            
        if final_subgraph["edges"]:
            context += "Relationships:\n"
            for edge in final_subgraph["edges"]:
                context += f"- {edge['from_node']} [{edge['relation']}] -> {edge['to_node']}\n"
                
        return context
