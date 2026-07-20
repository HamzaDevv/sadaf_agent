from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class EpisodicEvent(BaseModel):
    """Raw time-bound events logged from the conversation."""
    event_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    raw_text: str
    emotion: Optional[str] = None
    salience: float = 0.5  # Importance of the event
    contextual_triggers: List[str] = Field(default_factory=list)

class MemoryNode(BaseModel):
    """Semantic fact extracted from episodes."""
    node_id: str  # e.g., "career:company"
    section: str  # e.g., "career"
    key: str      # e.g., "company"
    value: str    # e.g., "Accenture"

    # Cognitive Attributes
    salience: float = 0.8        # Initial importance [0-1]
    stability: float = 1.0       # Memory resistance to decay (L >= 1.0)
    confidence: float = 1.0      # Truth probability [0-1]

    # Usage & Timing
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_accessed: datetime = Field(default_factory=datetime.now)
    access_count: int = 1

    # Metadata
    source_episode_id: Optional[str] = None
    status: str = "active"  # "active" | "provisional" | "archived"

class MemoryEdge(BaseModel):
    """Semantic relationship between two MemoryNodes."""
    from_node: str
    to_node: str
    relation: str  # e.g., "works_at", "supersedes"
    weight: float = 1.0  # Semantic association strength
    created_at: datetime = Field(default_factory=datetime.now)
    last_reinforced: datetime = Field(default_factory=datetime.now)
