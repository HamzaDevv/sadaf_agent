"""
memory/graph_store.py — Sadaf V6 Knowledge Graph & Vector Store

Replaces old static graph with a dynamic cognitive graph featuring:
- Pydantic schemas (MemoryNode, MemoryEdge, EpisodicEvent)
- Lazy evaluation for cognitive decay and archival
- ChromaDB vector storage with Gemini embeddings
"""

import os
import json
import math
from datetime import datetime
from typing import List, Dict, Any, Set, Tuple, Optional
from pathlib import Path
from config import MEMORY_DIR

import chromadb
from chromadb.config import Settings
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
import google.generativeai as genai
from dotenv import load_dotenv

# Load env vars for Gemini API Key
load_dotenv()

from memory.schemas import MemoryNode, MemoryEdge, EpisodicEvent

class GeminiEmbeddingFunction(EmbeddingFunction):
    def __init__(self):
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            print("[GraphStore] WARNING: GOOGLE_API_KEY not found. Embeddings will fail.")
        genai.configure(api_key=api_key)
        self.model = 'models/gemini-embedding-2'
        
    def __call__(self, input: Documents) -> Embeddings:
        embeddings = []
        for text in input:
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type="retrieval_document"
            )
            embeddings.append(result['embedding'])
        return embeddings

class MemoryGraphStore:
    def __init__(self, storage_dir: str = MEMORY_DIR):
        self.root = Path(storage_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=str(self.root / "chromadb"))
        self.embedding_fn = GeminiEmbeddingFunction()
        # Keep collections per user or a single collection. We'll do single collection, filtering by user_id
        self.collection = self.chroma_client.get_or_create_collection(
            name="memory_nodes",
            embedding_function=self.embedding_fn
        )

    def _user_dir(self, user_id: str) -> Path:
        return self.root / user_id

    def _graph_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "graph.json"

    def _archive_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "archive.json"

    def _episodes_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "episodes.json"

    def ensure_user_dir(self, user_id: str):
        user_dir = self._user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        
        graph_path = self._graph_path(user_id)
        if not graph_path.exists():
            empty_graph = {
                "user_id": user_id,
                "nodes": {},
                "edges": [],
                "sessions": []
            }
            graph_path.write_text(json.dumps(empty_graph, indent=2), encoding="utf-8")
            
        archive_path = self._archive_path(user_id)
        if not archive_path.exists():
            archive_path.write_text(json.dumps({"nodes": {}}, indent=2), encoding="utf-8")
            
        episodes_path = self._episodes_path(user_id)
        if not episodes_path.exists():
            episodes_path.write_text(json.dumps({"episodes": []}, indent=2), encoding="utf-8")

    def _load_json(self, path: Path, default: Dict) -> Dict:
        if not path.exists():
            return default
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Ensure keys from default exist in data
            for k, v in default.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception as e:
            print(f"[GraphStore] Error loading {path}: {e}")
            return default

    def _save_json(self, path: Path, data: Dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        try:
            # Custom encoder to handle datetime
            class DateTimeEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    return super().default(obj)
                    
            tmp.write_text(json.dumps(data, indent=2, cls=DateTimeEncoder), encoding="utf-8")
            tmp.rename(path)
        except Exception as e:
            print(f"[GraphStore] Error saving {path}: {e}")

    # --- EPISODIC MEMORY ---
    def append_episode(self, user_id: str, episode: EpisodicEvent):
        path = self._episodes_path(user_id)
        data = self._load_json(path, {"episodes": []})
        data["episodes"].append(episode.model_dump())
        self._save_json(path, data)

    # --- COGNITIVE LIFECYCLE (LAZY DECAY) ---
    def _evaluate_decay(self, node: MemoryNode) -> float:
        """Calculate effective weight: S * e^(-delta_t / (tau * L))"""
        # tau is time constant, say 30 days
        tau = 30.0
        now = datetime.now()
        delta_t = (now - node.last_accessed).total_seconds() / 86400.0 # in days
        if delta_t < 0:
            delta_t = 0
            
        weight = node.salience * math.exp(-delta_t / (tau * max(1.0, node.stability)))
        return weight

    def _lazy_prune(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Check all nodes for decay, archive those below threshold."""
        threshold = 0.15
        to_archive = []
        
        for nid, node_dict in data["nodes"].items():
            # Convert to model to safely access defaults if missing
            try:
                node = MemoryNode(**node_dict)
            except Exception:
                continue
                
            weight = self._evaluate_decay(node)
            if weight < threshold and node.status != "archived":
                to_archive.append((nid, node))
                
        if to_archive:
            archive_data = self._load_json(self._archive_path(user_id), {"nodes": {}})
            for nid, node in to_archive:
                node.status = "archived"
                archive_data["nodes"][nid] = node.model_dump()
                del data["nodes"][nid]
                
                # Remove from Chroma
                try:
                    self.collection.delete(ids=[f"{user_id}::{nid}"])
                except:
                    pass
                print(f"[GraphStore] Archived decayed node: {nid}")
                
            self._save_json(self._archive_path(user_id), archive_data)
            
            # Clean up edges
            archived_ids = set(nid for nid, _ in to_archive)
            data["edges"] = [
                e for e in data.get("edges", [])
                if e["from_node"] not in archived_ids and e["to_node"] not in archived_ids
            ]
            
        return data

    def _sync_to_chroma(self, user_id: str, node: MemoryNode):
        """Update node in ChromaDB."""
        doc_id = f"{user_id}::{node.node_id}"
        content = f"{node.section} {node.key} {node.value}"
        metadata = {"user_id": user_id, "node_id": node.node_id, "section": node.section}
        
        self.collection.upsert(
            documents=[content],
            metadatas=[metadata],
            ids=[doc_id]
        )

    # --- NODE & EDGE OPERATIONS ---
    def upsert_node(self, user_id: str, node_data: MemoryNode):
        data = self._load_json(self._graph_path(user_id), {"user_id": user_id, "nodes": {}, "edges": [], "sessions": []})
        data = self._lazy_prune(user_id, data)
        
        node_id = node_data.node_id
        if node_id in data["nodes"]:
            # Update existing
            existing = MemoryNode(**data["nodes"][node_id])
            existing.value = node_data.value
            existing.salience = node_data.salience
            existing.confidence = node_data.confidence
            existing.status = node_data.status
            existing.updated_at = datetime.now()
            existing.last_accessed = datetime.now()
            existing.access_count += 1
            # Stability boost formula: slow logarithmic growth
            existing.stability += 0.1
            node_data = existing
            print(f"[GraphStore] Updated node: {node_id} = {node_data.value} (Stability: {node_data.stability:.2f})")
        else:
            print(f"[GraphStore] Added node: {node_id} = {node_data.value}")
            
        data["nodes"][node_id] = node_data.model_dump()
        self._sync_to_chroma(user_id, node_data)
        self._save_json(self._graph_path(user_id), data)

    def access_node(self, user_id: str, node_id: str) -> Optional[MemoryNode]:
        """Retrieve a node and boost its stability."""
        data = self._load_json(self._graph_path(user_id), {"nodes": {}})
        if node_id in data.get("nodes", {}):
            node = MemoryNode(**data["nodes"][node_id])
            node.last_accessed = datetime.now()
            node.access_count += 1
            node.stability += 0.05  # minor boost for read access
            data["nodes"][node_id] = node.model_dump()
            self._save_json(self._graph_path(user_id), data)
            return node
        return None

    def add_edge(self, user_id: str, from_node: str, to_node: str, relation: str, weight: float = 1.0):
        data = self._load_json(self._graph_path(user_id), {"nodes": {}, "edges": []})
        data = self._lazy_prune(user_id, data)
        
        if from_node not in data["nodes"] or to_node not in data["nodes"]:
            return
            
        # Check if exists
        for edge in data["edges"]:
            if edge["from_node"] == from_node and edge["to_node"] == to_node and edge["relation"] == relation:
                edge["weight"] = min(1.0, edge.get("weight", 1.0) + 0.1) # Boost weight
                edge["last_reinforced"] = datetime.now()
                self._save_json(self._graph_path(user_id), data)
                return
                
        new_edge = MemoryEdge(
            from_node=from_node,
            to_node=to_node,
            relation=relation,
            weight=weight
        )
        data["edges"].append(new_edge.model_dump())
        print(f"[GraphStore] Added edge: {from_node} -[{relation}]-> {to_node}")
        self._save_json(self._graph_path(user_id), data)

    def get_all_nodes(self, user_id: str) -> Dict[str, Any]:
        data = self._load_json(self._graph_path(user_id), {"nodes": {}})
        data = self._lazy_prune(user_id, data)
        self._save_json(self._graph_path(user_id), data)
        return data.get("nodes", {})

    def get_nodes_summary(self, user_id: str) -> str:
        nodes = self.get_all_nodes(user_id)
        if not nodes:
            return "No existing facts."
        lines = [f"- {nid}: {n.get('key')} = {n.get('value')}" for nid, n in nodes.items()]
        return "\n".join(lines)

    # --- SEARCH & TRAVERSAL ---
    def vector_search(self, user_id: str, query: str, top_k: int = 5) -> List[str]:
        """Search using ChromaDB Gemini embeddings."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where={"user_id": user_id}
            )
            if results and results["metadatas"] and results["metadatas"][0]:
                return [m["node_id"] for m in results["metadatas"][0]]
        except Exception as e:
            print(f"[GraphStore] Vector search error: {e}")
        return []
        
    def get_subgraph(self, user_id: str, node_ids: List[str]) -> Dict[str, Any]:
        data = self._load_json(self._graph_path(user_id), {"nodes": {}, "edges": []})
        nodes = {nid: data["nodes"][nid] for nid in node_ids if nid in data["nodes"]}
        edges = []
        for edge in data["edges"]:
            if edge["from_node"] in node_ids or edge["to_node"] in node_ids:
                edges.append(edge)
        return {"nodes": nodes, "edges": edges}

    # --- SESSIONS ---
    def append_session(self, user_id: str, note: str):
        if not note: return
        data = self._load_json(self._graph_path(user_id), {"sessions": []})
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        data["sessions"].append(f"[{timestamp}] {note}")
        if len(data["sessions"]) > 10:
            data["sessions"] = data["sessions"][-10:]
        self._save_json(self._graph_path(user_id), data)

    def get_last_n_sessions(self, user_id: str, n: int = 5) -> str:
        data = self._load_json(self._graph_path(user_id), {"sessions": []})
        sessions = data.get("sessions", [])
        if not sessions: return ""
        return "# Recent Sessions\n" + "\n".join(f"- {s}" for s in sessions[-n:])
        
    def increment_conversation_count(self, user_id: str):
        data = self._load_json(self._graph_path(user_id), {"total_conversations": 0})
        data["total_conversations"] = data.get("total_conversations", 0) + 1
        self._save_json(self._graph_path(user_id), data)

    # --- VISUALIZATION ---
    def visualize(self, user_id: str):
        try:
            from pyvis.network import Network
        except ImportError:
            print("[GraphStore] pyvis not installed.")
            return

        data = self._load_json(self._graph_path(user_id), {"nodes": {}, "edges": []})
        if not data["nodes"]: return

        net = Network(height="750px", width="100%", bgcolor="#222222", font_color="white", directed=True)
        
        for node_id, node_dict in data["nodes"].items():
            try:
                node = MemoryNode(**node_dict)
                weight = self._evaluate_decay(node)
                
                label = f"{node.key}\n{node.value}"
                # Cognitive sizing: larger if high stability & salience
                size = max(10, 20 * (node.stability * node.salience))
                
                title = (f"Section: {node.section}\n"
                         f"Stability: {node.stability:.2f}\n"
                         f"Salience: {node.salience:.2f}\n"
                         f"Weight: {weight:.2f}\n"
                         f"Status: {node.status}")
                
                color = None
                borderWidth = 1
                borderWidthSelected = 2
                
                # Dim color if low confidence
                if node.confidence < 0.5:
                    color = {"background": "#555555", "border": "#333333"}
                
                # Dashed borders for provisional
                shapeProperties = {}
                if node.status == "provisional":
                    shapeProperties = {"borderDashes": [5, 5]}
                    borderWidth = 3
                    
                net.add_node(
                    node_id, 
                    label=label, 
                    title=title, 
                    group=node.section,
                    size=size,
                    color=color,
                    borderWidth=borderWidth,
                    shapeProperties=shapeProperties
                )
            except Exception as e:
                print(f"Skipping visualization for node {node_id}: {e}")
            
        for edge in data.get("edges", []):
            try:
                net.add_edge(edge["from_node"], edge["to_node"], title=edge["relation"], label=edge["relation"])
            except:
                pass
            
        out_path = self._user_dir(user_id) / "graph_viz.html"
        net.save_graph(str(out_path))
        print(f"[GraphStore] Saved visualization to {out_path}")
