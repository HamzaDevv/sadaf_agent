"""Dry-run-first importer for copied synthetic legacy graph fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from sadaf.memory import InvalidMemory, MemoryStore, _time


@dataclass(frozen=True)
class MigrationReport:
    applied: bool
    already_imported: bool
    facts: int
    edges: int
    episodes: int
    digest: str
    backup: str | None = None


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _read_json(source: Path, name: str) -> tuple[dict[str, Any], bytes]:
    path = source / name
    if path.is_symlink() or not path.is_file():
        return {}, b""
    if path.stat().st_size > 20_000_000:
        raise InvalidMemory(f"Legacy fixture file is too large: {name}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise InvalidMemory(f"Legacy fixture JSON is invalid: {name}") from None
    if not isinstance(value, dict):
        raise InvalidMemory(f"Legacy fixture root must be an object: {name}")
    return value, raw


def _legacy_node(node_id: str, item: Any, *, archived: bool = False) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise InvalidMemory("Legacy node must be an object")
    node_id = item.get("node_id", node_id)
    required = ("section", "key", "value")
    if not isinstance(node_id, str) or not node_id or any(not isinstance(item.get(k), str) or not item[k].strip() for k in required):
        raise InvalidMemory("Legacy node is missing its ID, section, key, or value")
    def score(name: str, default: float) -> float:
        value = item.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not 0 <= value <= 1:
            raise InvalidMemory(f"Legacy node {name} is out of range")
        return float(value)
    state = "archived" if archived or item.get("status") == "archived" else item.get("status", "active")
    if not isinstance(state,str): state="active"
    if state not in {"active", "provisional", "archived", "superseded", "expired"}:
        state = "active"
    durable=item.get("is_durable", item.get("section","").casefold() in {"identity","preferences"})
    if not isinstance(durable,bool): raise InvalidMemory("Legacy node durable flag must be boolean")
    stability=item.get("stability",1)
    if isinstance(stability,bool) or not isinstance(stability,(int,float)) or not math.isfinite(stability) or stability<0: raise InvalidMemory("Legacy node stability is invalid")
    source_episode=item.get("source_episode_id")
    if source_episode is not None and not isinstance(source_episode,str): raise InvalidMemory("Legacy source episode ID must be text")
    for timestamp in (item.get("created_at"),item.get("updated_at")):
        if timestamp is not None and not isinstance(timestamp,str): raise InvalidMemory("Legacy fact timestamps must be text")
        if timestamp is not None:
            _time(timestamp,"legacy timestamp")
    return {"node_id": node_id, "section": item["section"].strip(), "key": item["key"].strip(),
        "value": item["value"].strip(), "status": state, "confidence": score("confidence",1),
        "salience": score("salience",.8), "stability": stability,
        "is_durable": durable,
        "sensitivity": "personal", "allow_export": False,
        "source_episode_id": source_episode,
        "created_at": item.get("created_at"), "updated_at": item.get("updated_at")}


def _snapshot(source: Path) -> tuple[dict[str, Any], str]:
    components=[]
    graph, raw_graph = _read_json(source,"graph.json")
    archive, raw_archive = _read_json(source,"archive.json")
    episode_data, raw_episodes = _read_json(source,"episodes.json")
    if not any((raw_graph,raw_archive,raw_episodes)):
        raise InvalidMemory("Source has no legacy graph, archive, or episode JSON fixture")
    nodes=[]
    for raw, archived in ((graph.get("nodes",{}),False),(archive.get("nodes",{}),True)):
        if not isinstance(raw,dict): raise InvalidMemory("Legacy nodes field must be an object")
        for key,value in raw.items(): nodes.append(_legacy_node(key,value,archived=archived))
    # Archive entries take precedence if old files contain duplicate node IDs.
    unique={item["node_id"]:item for item in nodes}
    edge_values=graph.get("edges",[])
    if not isinstance(edge_values,list): raise InvalidMemory("Legacy edges field must be a list")
    edges=[]
    for edge in edge_values:
        if not isinstance(edge,dict): raise InvalidMemory("Legacy edge must be an object")
        a,b,relation=edge.get("from_node"),edge.get("to_node"),edge.get("relation")
        if not all(isinstance(v,str) and v for v in (a,b,relation)): raise InvalidMemory("Legacy edge is missing an endpoint or relation")
        weight=edge.get("weight",1)
        if isinstance(weight,bool) or not isinstance(weight,(int,float)) or not 0<=weight<=1: raise InvalidMemory("Legacy edge weight is out of range")
        if a in unique and b in unique: edges.append({"from_node":a,"to_node":b,"relation":relation,"weight":float(weight)})
    raw_events=episode_data.get("episodes",[])
    if not isinstance(raw_events,list): raise InvalidMemory("Legacy episodes field must be a list")
    episodes=[]
    for index,event in enumerate(raw_events):
        if not isinstance(event,dict): raise InvalidMemory("Legacy episode must be an object")
        eid=event.get("event_id") or event.get("id") or f"legacy-episode-{index}"
        raw_text=event.get("raw_text",event.get("text"))
        if not isinstance(eid,str) or not isinstance(raw_text,str) or not raw_text.strip(): raise InvalidMemory("Legacy episode is missing its ID or text")
        timestamp=event.get("timestamp")
        if timestamp is not None:
            if not isinstance(timestamp,str): raise InvalidMemory("Legacy episode timestamp must be text")
            _time(timestamp,"legacy episode timestamp")
        score=event.get("salience",.5)
        if isinstance(score,bool) or not isinstance(score,(int,float)) or not 0<=score<=1: raise InvalidMemory("Legacy episode salience is out of range")
        triggers=event.get("contextual_triggers",event.get("triggers",[]))
        if not isinstance(triggers,list) or any(not isinstance(v,str) for v in triggers): raise InvalidMemory("Legacy episode triggers must be text")
        emotion=event.get("emotion")
        if emotion is not None and not isinstance(emotion,str): raise InvalidMemory("Legacy episode emotion must be text")
        episodes.append({"event_id":eid,"timestamp":event.get("timestamp"),"raw_text":raw_text,"emotion":event.get("emotion"),"salience":float(score),"triggers":triggers})
    sessions=graph.get("sessions",[])
    if not isinstance(sessions,list) or any(not isinstance(s,str) for s in sessions): raise InvalidMemory("Legacy sessions must be text entries")
    for name,raw in (("graph.json",raw_graph),("archive.json",raw_archive),("episodes.json",raw_episodes)):
        components.append(name.encode()+b"\0"+raw)
    digest=hashlib.sha256(b"\0".join(components)).hexdigest()
    return {"nodes":list(unique.values()),"edges":edges,"episodes":episodes,"sessions":sessions},digest


def migrate_legacy(source: str | Path, target: str | Path, *, user_id: str = "default",
                   apply: bool = False, legacy_root: str | Path | None = None) -> MigrationReport:
    """Plan by default. Applying imports a copied tree to a separate database.

    `legacy_root` defaults to this checkout's real memories directory. Neither
    it nor any parent/child path can be used as source or destination.
    """
    source_path=Path(source).expanduser().resolve()
    target_path=Path(target).expanduser().resolve()
    protected=Path(legacy_root).expanduser().resolve() if legacy_root else Path(__file__).resolve().parents[1]/"memories"
    protected=protected.resolve()
    if _inside(source_path,protected) or _inside(protected,source_path): raise InvalidMemory("Source overlaps the configured legacy memory directory")
    if _inside(target_path,protected) or _inside(protected,target_path): raise InvalidMemory("Target overlaps the configured legacy memory directory")
    if _inside(source_path,target_path) or _inside(target_path,source_path): raise InvalidMemory("Source and target must be separate")
    if not source_path.is_dir(): raise InvalidMemory("Source must be a copied legacy fixture directory")
    snapshot,digest=_snapshot(source_path)
    source_key=hashlib.sha256(str(source_path).encode()).hexdigest()
    counts=(len(snapshot["nodes"]),len(snapshot["edges"]),len(snapshot["episodes"])+len(snapshot["sessions"]))
    if not apply:
        return MigrationReport(False,False,*counts,digest)
    backup=None
    if target_path.exists():
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path=target_path.with_name(target_path.name+f".backup-{stamp}")
        backup=str(MemoryStore.backup_database(target_path,backup_path))
    store=MemoryStore(target_path)
    imported, facts, edges, episodes=store._import_snapshot(user_id,snapshot,source_key=source_key,digest=digest)
    if not imported: return MigrationReport(True,True,0,0,0,digest,backup)
    return MigrationReport(True,False,facts,edges,episodes,digest,backup)
