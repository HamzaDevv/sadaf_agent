"""
memory/consolidator.py — Sadaf V6 Graph Memory Consolidator

Extracts episodic and semantic facts.
Handles soft contradictions by adjusting confidence and creating provisional supersedes edges.
Evaluates provisional nodes lazily.
"""
import uuid
import asyncio
from memory.graph_store import MemoryGraphStore
from memory.extractor import extract_facts
from memory.schemas import EpisodicEvent, MemoryNode

class MemoryConsolidator:
    def __init__(self, graph_store: MemoryGraphStore):
        self.store = graph_store

    async def consolidate(self, user_id: str, user_input: str, ai_response: str):
        """
        Consolidation pipeline:
          1. Extract episodic and semantic facts
          2. Log Episodic Event
          3. Process soft contradictions (belief updating)
          4. Upsert Semantic Nodes
          5. Add Edges
          6. Lazy Evaluate Provisional Nodes
        """
        try:
            # Stage 0: Fetch existing nodes summary for comparison
            existing_summary = await asyncio.to_thread(self.store.get_nodes_summary, user_id)

            # Stage 1: Extract facts
            patch = await extract_facts(user_input, ai_response, existing_summary)

            ep_data = patch.get("episodic_event")
            facts = patch.get("facts", [])
            edges = patch.get("edges", [])
            contradictions = patch.get("contradictions", [])
            session_note = patch.get("session_note")

            # Stage 2: Append Episodic
            if ep_data:
                ep = EpisodicEvent(
                    event_id=str(uuid.uuid4()),
                    raw_text=ep_data.get("raw_text", ""),
                    emotion=ep_data.get("emotion"),
                    salience=ep_data.get("salience", 0.5),
                    contextual_triggers=ep_data.get("contextual_triggers", [])
                )
                await asyncio.to_thread(self.store.append_episode, user_id, ep)

            # Stage 3: Handle Contradictions (Belief Updating)
            for c in contradictions:
                node_id = c.get("node_id")
                new_val = c.get("new_value")
                salience = c.get("salience", 0.5)
                
                if not node_id or ":" not in node_id or not new_val:
                    continue
                    
                sec, k = node_id.split(":", 1)
                
                # 1. Lower confidence of old node
                old_node = await asyncio.to_thread(self.store.access_node, user_id, node_id)
                if old_node:
                    old_node.confidence = max(0.1, old_node.confidence - 0.3)
                    await asyncio.to_thread(self.store.upsert_node, user_id, old_node)
                    
                # 2. Create provisional node
                prov_key = f"{k}_prov"
                prov_id = f"{sec}:{prov_key}"
                
                prov_node = MemoryNode(
                    node_id=prov_id,
                    section=sec,
                    key=prov_key,
                    value=new_val,
                    salience=salience,
                    status="provisional"
                )
                await asyncio.to_thread(self.store.upsert_node, user_id, prov_node)
                
                # 3. Add supersedes edge
                await asyncio.to_thread(self.store.add_edge, user_id, prov_id, node_id, "supersedes")
                print(f"[Consolidator] Created provisional contradiction: {prov_id} -[supersedes]-> {node_id}")

            # Stage 4: Upsert Nodes
            for fact in facts:
                sec = fact.get("section", "")
                k = fact.get("key", "")
                v = fact.get("value", "")
                s = fact.get("salience", 0.5)
                
                if sec and k and v:
                    nid = f"{sec.lower()}:{k.lower().replace(' ', '_')}"
                    # Check if this reinforces a provisional node
                    prov_id = f"{sec.lower()}:{k.lower().replace(' ', '_')}_prov"
                    existing_nodes = await asyncio.to_thread(self.store.get_all_nodes, user_id)
                    
                    if prov_id in existing_nodes:
                        # Reinforce the supersedes edge to trigger lazy promotion
                        await asyncio.to_thread(self.store.add_edge, user_id, prov_id, nid, "supersedes")
                    else:
                        node = MemoryNode(
                            node_id=nid,
                            section=sec,
                            key=k,
                            value=v,
                            salience=s,
                            status="active"
                        )
                        await asyncio.to_thread(self.store.upsert_node, user_id, node)

            # Stage 5: Add Edges
            for edge in edges:
                from_key = edge.get("from_key")
                from_sec = edge.get("from_section")
                to_key = edge.get("to_key")
                to_sec = edge.get("to_section")
                relation = edge.get("relation")
                
                if from_key and from_sec and to_key and to_sec and relation:
                    from_id = f"{from_sec.lower()}:{from_key.lower().replace(' ', '_')}"
                    to_id = f"{to_sec.lower()}:{to_key.lower().replace(' ', '_')}"
                    await asyncio.to_thread(self.store.add_edge, user_id, from_id, to_id, relation)

            # Stage 6: Append session note
            if session_note:
                await asyncio.to_thread(self.store.append_session, user_id, session_note)
                
            await asyncio.to_thread(self.store.increment_conversation_count, user_id)
            
            # Stage 7: Lazy evaluate provisional nodes
            await asyncio.to_thread(self._evaluate_provisional_nodes, user_id)

        except Exception as e:
            print(f"[Consolidator] Error: {e}")

    def _evaluate_provisional_nodes(self, user_id: str):
        """
        Check if any provisional nodes have been reinforced enough (weight >= 1.2)
        to replace the old node they supersede.
        """
        path = self.store._graph_path(user_id)
        data = self.store._load_json(path, {"nodes": {}, "edges": []})
        
        edges = data.get("edges", [])
        nodes = data.get("nodes", {})
        
        to_remove_edges = []
        
        for edge in edges:
            if edge.get("relation") == "supersedes":
                if edge.get("weight", 1.0) >= 1.15: # ~2 reinforcements
                    prov_id = edge["from_node"]
                    old_id = edge["to_node"]
                    
                    if prov_id in nodes and old_id in nodes:
                        prov_dict = nodes[prov_id]
                        
                        # Archive old
                        old_node = MemoryNode(**nodes[old_id])
                        old_node.status = "archived"
                        
                        archive_path = self.store._archive_path(user_id)
                        archive_data = self.store._load_json(archive_path, {"nodes": {}})
                        archive_data["nodes"][old_id] = old_node.model_dump()
                        self.store._save_json(archive_path, archive_data)
                        
                        # Overwrite old node ID with new provisional data, making it active
                        new_active = MemoryNode(**prov_dict)
                        new_active.node_id = old_id
                        new_active.key = old_node.key
                        new_active.status = "active"
                        
                        nodes[old_id] = new_active.model_dump()
                        
                        # Remove the provisional node ID
                        del nodes[prov_id]
                        to_remove_edges.append(edge)
                        
                        # Clean ChromaDB
                        try:
                            self.store.collection.delete(ids=[f"{user_id}::{prov_id}"])
                            self.store._sync_to_chroma(user_id, new_active)
                        except: pass
                        
                        print(f"[Consolidator] Lazy belief update: {prov_id} replaced {old_id}")

        if to_remove_edges:
            data["edges"] = [e for e in edges if e not in to_remove_edges]
            self.store._save_json(path, data)
