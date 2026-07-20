import os
import sys
import re

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from memory.graph_store import MemoryGraphStore
from config import DEFAULT_USER_ID

def migrate():
    print(f"Migrating memories for {DEFAULT_USER_ID}...")
    store = MemoryGraphStore()
    user_dir = store._user_dir(DEFAULT_USER_ID)
    
    # Check if md files exist
    if not user_dir.exists():
        print(f"User directory not found: {user_dir}")
        return
        
    for filename in os.listdir(user_dir):
        if filename.endswith(".md") and filename not in ["_index.md", "sessions.md"]:
            section = filename.replace(".md", "")
            if section == "sadaf_user":
                continue # Skip the orphaned monolith file
                
            filepath = user_dir / filename
            content = filepath.read_text(encoding="utf-8")
            
            # Find all `- **Key**: Value`
            matches = re.findall(r"- \*\*(.+?)\*\*: (.+)", content)
            for key, value in matches:
                value = value.strip()
                if value and value.lower() not in ["unknown", "null", "not explicitly stated", "[]"]:
                    store.upsert_node(DEFAULT_USER_ID, section, key, value)
                    
        elif filename == "sessions.md":
            filepath = user_dir / filename
            content = filepath.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("- ["):
                    # e.g., "- [2026-07-20 15:40] User agreed to a personal conversation..."
                    match = re.search(r"- \[(.+?)\] (.+)", line)
                    if match:
                        _, note = match.groups()
                        store.append_session(DEFAULT_USER_ID, note)
                        
    print("Migration complete. Generating visualization...")
    store.visualize(DEFAULT_USER_ID)

if __name__ == "__main__":
    migrate()
