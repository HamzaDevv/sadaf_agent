import os
from memory.schemas import MemoryNode, MemoryEdge
from tests.utils.fixtures import get_isolated_subsystems, cleanup_isolated_data

def test_root_path_creation():
    run_id = "test_memory_0"
    try:
        store, _, _, _, _ = get_isolated_subsystems(run_id)
        assert os.path.exists(store.root)
    finally:
        cleanup_isolated_data(run_id)

def test_node_upsert_and_retrieve():
    run_id = "test_memory_1"
    try:
        store, _, _, _, _ = get_isolated_subsystems(run_id)
        user_id = "test_user"
        store.ensure_user_dir(user_id)
        
        node = MemoryNode(
            node_id="identity:name",
            section="identity",
            key="name",
            value="Alex"
        )
        store.upsert_node(user_id, node)
        nid = node.node_id
        
        retrieved = store.get_all_nodes(user_id)
        assert nid in retrieved
        assert retrieved[nid]["value"] == "Alex"
    finally:
        cleanup_isolated_data(run_id)

def test_graph_edges_persist():
    run_id = "test_memory_2"
    try:
        store, _, _, _, _ = get_isolated_subsystems(run_id)
        user_id = "test_user"
        store.ensure_user_dir(user_id)
        
        n1 = MemoryNode(node_id="identity:name", section="identity", key="name", value="Alex")
        n2 = MemoryNode(node_id="pet:dog", section="pet", key="dog", value="Max")
        store.upsert_node(user_id, n1)
        store.upsert_node(user_id, n2)
        
        store.add_edge(user_id, n1.node_id, n2.node_id, relation="owns", weight=1.0)
        
        # Load from disk to verify persistence
        graph_data = store._load_json(store._graph_path(user_id), {"nodes": {}, "edges": []})
        assert len(graph_data["edges"]) == 1
        edge = graph_data["edges"][0]
        assert edge["from_node"] == n1.node_id
        assert edge["to_node"] == n2.node_id
        assert edge["relation"] == "owns"
    finally:
        cleanup_isolated_data(run_id)

async def test_consolidation_creates_nodes():
    run_id = "test_memory_3"
    try:
        store, _, consolidator, _, _ = get_isolated_subsystems(run_id)
        user_id = "test_user"
        store.ensure_user_dir(user_id)
        
        await consolidator.consolidate(user_id, "I live in New York and I love pizza.", "Oh, New York has great pizza!")
        
        nodes = store.get_all_nodes(user_id)
        # Should have extracted at least location and preference
        found_location = any("New York" in str(n) for n in nodes.values())
        found_preference = any("pizza" in str(n).lower() for n in nodes.values())
        
        assert found_location, "Failed to extract location"
        assert found_preference, "Failed to extract preference"
    finally:
        cleanup_isolated_data(run_id)
