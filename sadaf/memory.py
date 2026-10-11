"""Transactional scoped memory. Importing this module performs no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid
from typing import Any, Iterable, Mapping, Protocol


SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes(
 id TEXT NOT NULL,user_id TEXT NOT NULL,project_id TEXT,turn_id TEXT,recorded_at TEXT NOT NULL,
 raw_text TEXT NOT NULL,emotion TEXT,salience REAL NOT NULL CHECK(salience BETWEEN 0 AND 1),triggers_json TEXT NOT NULL,
 PRIMARY KEY(user_id,id),UNIQUE(id,user_id));
CREATE INDEX IF NOT EXISTS episode_scope_time ON episodes(user_id,project_id,recorded_at DESC);
CREATE TABLE IF NOT EXISTS facts(
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL,project_id TEXT,scope_key TEXT NOT NULL,
 section TEXT NOT NULL,section_key TEXT NOT NULL,fact_key TEXT NOT NULL,key_norm TEXT NOT NULL,value TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('provisional','confirmed','superseded','expired','archived')),
 confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),salience REAL NOT NULL CHECK(salience BETWEEN 0 AND 1),
 stability REAL NOT NULL CHECK(stability>=0),is_durable INTEGER NOT NULL CHECK(is_durable IN (0,1)),
 sensitivity TEXT NOT NULL CHECK(sensitivity IN ('public','personal','sensitive')),
 allow_export INTEGER NOT NULL CHECK(allow_export IN (0,1)),source_turn_id TEXT,
 source_episode_id TEXT,effective_at TEXT,expires_at TEXT,
 legacy_node_id TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(user_id,scope_key,legacy_node_id),
 FOREIGN KEY(source_episode_id,user_id) REFERENCES episodes(id,user_id));
CREATE INDEX IF NOT EXISTS fact_scope_state ON facts(user_id,scope_key,status);
CREATE INDEX IF NOT EXISTS fact_evidence ON facts(source_episode_id,source_turn_id);
CREATE TABLE IF NOT EXISTS revisions(
 id INTEGER PRIMARY KEY,fact_id TEXT NOT NULL,user_id TEXT NOT NULL,scope_key TEXT NOT NULL,action TEXT NOT NULL,
 recorded_at TEXT NOT NULL,source_turn_id TEXT,before_json TEXT,after_json TEXT);
CREATE TABLE IF NOT EXISTS edges(
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL,project_id TEXT,scope_key TEXT NOT NULL,
 from_fact_id TEXT NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
 to_fact_id TEXT NOT NULL REFERENCES facts(id) ON DELETE CASCADE,relation TEXT NOT NULL,
 weight REAL NOT NULL CHECK(weight BETWEEN 0 AND 1),created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(user_id,scope_key,from_fact_id,to_fact_id,relation));
CREATE TABLE IF NOT EXISTS extraction_jobs(
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL,project_id TEXT,scope_key TEXT NOT NULL,turn_id TEXT,episode_id TEXT,
 input_text TEXT,patch_json TEXT,status TEXT NOT NULL CHECK(status IN ('queued','processing','applied','no_facts','failed','cancelled')),
 error_code TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS extraction_queue ON extraction_jobs(status,created_at);
CREATE TABLE IF NOT EXISTS forgotten_values(
 user_id TEXT NOT NULL,scope_key TEXT NOT NULL,section_key TEXT NOT NULL,key_norm TEXT NOT NULL,value_hash TEXT NOT NULL,
 forgotten_at TEXT NOT NULL,PRIMARY KEY(user_id,scope_key,section_key,key_norm,value_hash));
CREATE TABLE IF NOT EXISTS migration_imports(
 source_key TEXT NOT NULL,digest TEXT NOT NULL,user_id TEXT NOT NULL,imported_at TEXT NOT NULL,
 fact_count INTEGER NOT NULL,edge_count INTEGER NOT NULL,episode_count INTEGER NOT NULL,
 PRIMARY KEY(source_key,digest,user_id));
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
 fact_id UNINDEXED,user_id UNINDEXED,scope_key UNINDEXED,section,fact_key,value,
 tokenize='unicode61 remove_diacritics 2');
"""


class MemoryErrorBase(ValueError):
    """A safe validation or lifecycle error."""


class InvalidMemory(MemoryErrorBase):
    pass


class JobNotRunnable(MemoryErrorBase):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _time(value: str | datetime | None, name: str) -> str | None:
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise InvalidMemory(f"{name} must be an ISO-8601 timestamp") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _text(value: Any, name: str, maximum: int = 2000) -> str:
    if not isinstance(value, str):
        raise InvalidMemory(f"{name} must be text")
    value = value.strip()
    if not value or len(value) > maximum or "\x00" in value:
        raise InvalidMemory(f"{name} must be nonempty and at most {maximum} characters")
    return value


def _score(value: Any, name: str, upper: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= upper:
        raise InvalidMemory(f"{name} must be between 0 and {upper}")
    return float(value)


def _scope(project_id: str | None) -> str:
    return "global" if project_id is None else "project:" + _text(project_id, "project_id", 300)


def _digest_value(value: str) -> str:
    return hashlib.sha256(value.strip().casefold().encode()).hexdigest()


@dataclass(frozen=True)
class Fact:
    id: str
    user_id: str
    project_id: str | None
    section: str
    key: str
    value: str
    status: str
    confidence: float
    salience: float
    stability: float
    is_durable: bool
    sensitivity: str
    allow_export: bool
    source_turn_id: str | None
    source_episode_id: str | None
    effective_at: str | None
    expires_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Episode:
    id: str
    user_id: str
    project_id: str | None
    turn_id: str | None
    recorded_at: str
    raw_text: str
    emotion: str | None
    salience: float
    triggers: tuple[str, ...]


@dataclass(frozen=True)
class Edge:
    id: str
    user_id: str
    project_id: str | None
    from_fact_id: str
    to_fact_id: str
    relation: str
    weight: float


@dataclass(frozen=True)
class Recall:
    facts: tuple[Fact, ...]
    profile_overrides: tuple[tuple[str, str, str], ...]


class MemoryRepository(Protocol):
    """Contract for scoped memory consumers; providers never own persistence."""

    def add_episode(self, user_id: str, raw_text: str, **metadata: Any) -> Episode: ...
    def record_fact(self, user_id: str, section: str, key: str, value: str, **metadata: Any) -> str: ...
    def get_fact(self, user_id: str, fact_id: str) -> Fact | None: ...
    def list_facts(self, user_id: str, **scope: Any) -> tuple[Fact, ...]: ...
    def correct_fact(self, old_fact_id: str, value: str, *, source_turn_id: str) -> str: ...
    def expire_fact(self, fact_id: str, *, source_turn_id: str | None = None) -> bool: ...
    def forget_fact(self, fact_id: str) -> bool: ...
    def add_edge(self, user_id: str, from_fact_id: str, to_fact_id: str, relation: str, **scope: Any) -> str: ...
    def recall(self, user_id: str, query: str, **scope: Any) -> Recall: ...
    def enqueue_extraction(self, user_id: str, input_text: str, **metadata: Any) -> str: ...
    def apply_extraction_patch(self, job_id: str, patch: Mapping[str, Any]) -> tuple[str, ...]: ...


def _fact(row: sqlite3.Row) -> Fact:
    return Fact(row["id"],row["user_id"],row["project_id"],row["section"],row["fact_key"],row["value"],row["status"],
        row["confidence"],row["salience"],row["stability"],bool(row["is_durable"]),row["sensitivity"],bool(row["allow_export"]),
        row["source_turn_id"],row["source_episode_id"],row["effective_at"],row["expires_at"],row["created_at"],row["updated_at"])


class MemoryStore:
    """Database creation is explicit; operations use independent SQLite transactions."""

    def __init__(self, database: str | Path, *, profile_path: str | Path | None = None,
                 persona_path: str | Path | None = None):
        if str(database) == ":memory:":
            raise InvalidMemory("A database file is required for restart-safe storage")
        self.database = Path(database).expanduser().resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        configured_profile = Path(profile_path).expanduser().absolute() if profile_path else self.database.parent / "profiles" / "{user_id}.md"
        self._profile_template = "{user_id}" in str(configured_profile)
        self._profile_pattern = str(configured_profile)
        self.profile_path = self._profile_for("default") if self._profile_template else configured_profile.resolve()
        configured_persona=Path(persona_path).expanduser().absolute() if persona_path else self.database.parent / "persona.md"
        if configured_persona.is_symlink(): raise InvalidMemory("Persona path cannot be a symlink")
        self.persona_path=configured_persona.resolve()
        if self.database.parent not in self.profile_path.parents or self.database.parent not in self.persona_path.parents:
            raise InvalidMemory("Profile and persona paths must stay inside the memory data directory")
        if self.profile_path == self.persona_path:
            raise InvalidMemory("Profile and persona paths must be separate")
        self._ensure_file(self.profile_path,"# Global user profile\n\n## Preferences\n\n")
        self._ensure_file(self.persona_path,"# Sadaf persona\n\n")
        self._initialize()

    def _profile_for(self, user_id: str) -> Path:
        if not self._profile_template:
            return Path(self._profile_pattern)
        slug=re.sub(r"[^a-zA-Z0-9_-]+","_",user_id)[:48] or "user"
        tag=hashlib.sha256(user_id.encode()).hexdigest()[:8]
        candidate=Path(self._profile_pattern.replace("{user_id}",f"{slug}-{tag}"))
        if candidate.is_symlink(): raise InvalidMemory("Profile path cannot be a symlink")
        resolved=candidate.resolve()
        if self.database.parent not in resolved.parents: raise InvalidMemory("Profile path must stay inside the memory data directory")
        return resolved

    @staticmethod
    def _ensure_file(path: Path, starter: str) -> None:
        path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with path.open("x",encoding="utf-8") as stream:
                stream.write(starter)
        except FileExistsError:
            if not path.is_file(): raise InvalidMemory("Profile and persona paths must be files")

    @classmethod
    def from_settings(cls, settings: Any) -> "MemoryStore":
        """Construct the canonical store only after the caller explicitly opts in."""
        return cls(settings.data_dir / "memory.sqlite3", profile_path=settings.profile_path,
                   persona_path=settings.persona_path)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _initialize(self) -> None:
        db = self._connect()
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            db.execute("PRAGMA user_version=1")
        finally:
            db.close()

    def _write(self) -> sqlite3.Connection:
        db = self._connect()
        db.execute("BEGIN IMMEDIATE")
        return db

    @staticmethod
    def _end(db: sqlite3.Connection, error: BaseException | None = None) -> None:
        try:
            db.rollback() if error else db.commit()
        finally:
            db.close()

    def add_episode(self, user_id: str, raw_text: str, *, project_id: str | None = None,
                    turn_id: str | None = None, episode_id: str | None = None,
                    recorded_at: str | datetime | None = None, emotion: str | None = None,
                    salience: float = 0.5, triggers: Iterable[str] = ()) -> Episode:
        user_id=_text(user_id,"user_id",300); raw_text=_text(raw_text,"raw_text",100_000)
        project_id=_text(project_id,"project_id",300) if project_id is not None else None
        turn_id=_text(turn_id,"turn_id",300) if turn_id else None
        episode_id=_text(episode_id,"episode_id",300) if episode_id else str(uuid.uuid4())
        emotion=_text(emotion,"emotion",300) if emotion else None
        triggers=tuple(_text(t,"trigger",500) for t in triggers)
        recorded=_time(recorded_at,"recorded_at") or _now(); salience=_score(salience,"salience")
        db=self._write()
        try:
            db.execute("INSERT INTO episodes VALUES (?,?,?,?,?,?,?,?,?)",(episode_id,user_id,project_id,turn_id,recorded,raw_text,emotion,salience,json.dumps(triggers)))
            self._end(db)
        except BaseException as exc:
            self._end(db,exc); raise
        return Episode(episode_id,user_id,project_id,turn_id,recorded,raw_text,emotion,salience,triggers)

    def get_episode(self, user_id: str, episode_id: str) -> Episode | None:
        with self._connect() as db:
            row=db.execute("SELECT * FROM episodes WHERE user_id=? AND id=?",(user_id,episode_id)).fetchone()
        return Episode(row["id"],row["user_id"],row["project_id"],row["turn_id"],row["recorded_at"],row["raw_text"],row["emotion"],row["salience"],tuple(json.loads(row["triggers_json"]))) if row else None

    def _values(self, *, fact_id: str, user_id: str, project_id: str | None, section: str, key: str, value: str,
                status: str, confidence: float, salience: float, stability: float, is_durable: bool,
                sensitivity: str, allow_export: bool, source_turn_id: str | None,
                source_episode_id: str | None, effective_at: str | datetime | None,
                expires_at: str | datetime | None, legacy_node_id: str | None = None,
                created_at: str | datetime | None = None, updated_at: str | datetime | None = None) -> tuple[Any,...]:
        user_id=_text(user_id,"user_id",300); project_id=_text(project_id,"project_id",300) if project_id is not None else None
        section=_text(section,"section",300); key=_text(key,"key",300); value=_text(value,"value",20_000)
        if status not in {"provisional","confirmed","archived"}: raise InvalidMemory("invalid fact status")
        if sensitivity not in {"public","personal","sensitive"}: raise InvalidMemory("invalid sensitivity")
        if not isinstance(is_durable,bool) or not isinstance(allow_export,bool): raise InvalidMemory("durable and export permission must be boolean")
        if isinstance(stability,bool) or not isinstance(stability,(int,float)) or not math.isfinite(stability) or stability<0: raise InvalidMemory("stability must be finite and nonnegative")
        return (fact_id,user_id,project_id,_scope(project_id),section,section.casefold(),key,key.casefold(),value,status,
            _score(confidence,"confidence"),_score(salience,"salience"),float(stability),int(is_durable),sensitivity,int(allow_export),
            _text(source_turn_id,"source_turn_id",300) if source_turn_id else None,
            _text(source_episode_id,"source_episode_id",300) if source_episode_id else None,
            _time(effective_at,"effective_at"),_time(expires_at,"expires_at"),
            _text(legacy_node_id,"legacy_node_id",1000) if legacy_node_id else None,_time(created_at,"created_at") or _now(),_time(updated_at,"updated_at") or _now())

    @staticmethod
    def _revision(db: sqlite3.Connection, row: Mapping[str,Any] | None, *, fact_id: str, user_id: str,
                  scope_key: str, action: str, turn_id: str | None, after: Mapping[str,Any] | None) -> None:
        db.execute("INSERT INTO revisions(fact_id,user_id,scope_key,action,recorded_at,source_turn_id,before_json,after_json) VALUES (?,?,?,?,?,?,?,?)",
            (fact_id,user_id,scope_key,action,_now(),turn_id,json.dumps(dict(row),default=str) if row else None,json.dumps(dict(after),default=str) if after else None))

    @staticmethod
    def _unindex(db: sqlite3.Connection, fact_id: str) -> None:
        row=db.execute("SELECT rowid FROM facts WHERE id=?",(fact_id,)).fetchone()
        if row: db.execute("DELETE FROM facts_fts WHERE rowid=?",(row[0],))

    def _put(self, db: sqlite3.Connection, values: tuple[Any,...], *, action: str,
             source_turn_id: str | None = None, supersedes: str | None = None) -> str:
        names=("id","user_id","project_id","scope_key","section","section_key","fact_key","key_norm","value","status","confidence","salience","stability","is_durable","sensitivity","allow_export","source_turn_id","source_episode_id","effective_at","expires_at","legacy_node_id","created_at","updated_at")
        new=dict(zip(names,values)); fid=new["id"]
        forgotten=db.execute("SELECT 1 FROM forgotten_values WHERE user_id=? AND scope_key=? AND section_key=? AND key_norm=? AND value_hash=?",(new["user_id"],new["scope_key"],new["section_key"],new["key_norm"],_digest_value(new["value"]))).fetchone()
        if forgotten:
            if action=="legacy_import" or new["status"]!="confirmed" or not source_turn_id:
                raise InvalidMemory("forgotten values require explicit confirmation with source turn evidence")
            db.execute("DELETE FROM forgotten_values WHERE user_id=? AND scope_key=? AND section_key=? AND key_norm=? AND value_hash=?",(new["user_id"],new["scope_key"],new["section_key"],new["key_norm"],_digest_value(new["value"])))
        if new["source_episode_id"]:
            episode=db.execute("SELECT 1 FROM episodes WHERE id=? AND user_id=? AND project_id IS ?",(new["source_episode_id"],new["user_id"],new["project_id"])).fetchone()
            if not episode: raise InvalidMemory("source episode must match the fact's user and project scope")
        to_supersede=[]
        if supersedes:
            row=db.execute("SELECT * FROM facts WHERE id=? AND user_id=? AND scope_key=?",(supersedes,new["user_id"],new["scope_key"])).fetchone()
            if not row or row["section_key"]!=new["section_key"] or row["key_norm"]!=new["key_norm"]: raise InvalidMemory("correction must target an active fact with the same key and scope")
            to_supersede=db.execute("SELECT * FROM facts WHERE user_id=? AND scope_key=? AND section_key=? AND key_norm=? AND status IN ('provisional','confirmed') AND id<>?",(new["user_id"],new["scope_key"],new["section_key"],new["key_norm"],fid)).fetchall()
        elif new["status"]=="confirmed":
            to_supersede=db.execute("SELECT * FROM facts WHERE user_id=? AND scope_key=? AND section_key=? AND key_norm=? AND status IN ('provisional','confirmed') AND id<>?",(new["user_id"],new["scope_key"],new["section_key"],new["key_norm"],fid)).fetchall()
        now=new["updated_at"]
        for old in to_supersede:
            before=dict(old)
            db.execute("UPDATE facts SET status='superseded',updated_at=? WHERE id=?",(now,old["id"]))
            self._unindex(db,old["id"])
            self._revision(db,before,fact_id=old["id"],user_id=new["user_id"],scope_key=new["scope_key"],action="superseded",turn_id=source_turn_id,after={**before,"status":"superseded","updated_at":now})
        prior=db.execute("SELECT * FROM facts WHERE id=?",(fid,)).fetchone()
        if prior and (prior["user_id"] != new["user_id"] or prior["scope_key"] != new["scope_key"]):
            raise InvalidMemory("fact ID already belongs to another user or scope")
        if prior:
            before=dict(prior)
            cols=names[2:21]+["updated_at"]
            db.execute("UPDATE facts SET "+",".join(f"{c}=?" for c in cols)+" WHERE id=?",tuple(new[c] for c in cols)+(fid,))
            self._unindex(db,fid)
        else:
            db.execute("INSERT INTO facts VALUES ("+",".join("?" for _ in values)+")",values)
            before=None
        self._revision(db,before,fact_id=fid,user_id=new["user_id"],scope_key=new["scope_key"],action=action,turn_id=source_turn_id,after=new)
        if new["status"] in {"provisional","confirmed"}:
            row=db.execute("SELECT rowid FROM facts WHERE id=?",(fid,)).fetchone()
            db.execute("INSERT INTO facts_fts(rowid,fact_id,user_id,scope_key,section,fact_key,value) VALUES (?,?,?,?,?,?,?)",(row[0],fid,new["user_id"],new["scope_key"],new["section"],new["fact_key"],new["value"]))
        return fid

    def record_fact(self, user_id: str, section: str, key: str, value: str, *, project_id: str | None = None,
                    fact_id: str | None = None, status: str = "provisional", confidence: float = .5,
                    salience: float = .5, stability: float = 1, is_durable: bool = False,
                    sensitivity: str = "personal", allow_export: bool = False,
                    source_turn_id: str | None = None, source_episode_id: str | None = None,
                    effective_at: str | datetime | None = None, expires_at: str | datetime | None = None,
                    legacy_node_id: str | None = None) -> str:
        fact_id=_text(fact_id,"fact_id",300) if fact_id else str(uuid.uuid4())
        values=self._values(fact_id=fact_id,user_id=user_id,project_id=project_id,section=section,key=key,value=value,status=status,confidence=confidence,salience=salience,stability=stability,is_durable=is_durable,sensitivity=sensitivity,allow_export=allow_export,source_turn_id=source_turn_id,source_episode_id=source_episode_id,effective_at=effective_at,expires_at=expires_at,legacy_node_id=legacy_node_id)
        db=self._write()
        try: self._put(db,values,action="record",source_turn_id=source_turn_id); self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return fact_id

    def correct_fact(self, old_fact_id: str, value: str, *, source_turn_id: str) -> str:
        db=self._write()
        try:
            old=db.execute("SELECT * FROM facts WHERE id=?",(old_fact_id,)).fetchone()
            if not old or old["status"] not in {"provisional","confirmed"}: raise InvalidMemory("only an active fact can be corrected")
            fid=str(uuid.uuid4())
            values=self._values(fact_id=fid,user_id=old["user_id"],project_id=old["project_id"],section=old["section"],key=old["fact_key"],value=value,status="confirmed",confidence=1,salience=old["salience"],stability=old["stability"],is_durable=bool(old["is_durable"]),sensitivity=old["sensitivity"],allow_export=bool(old["allow_export"]),source_turn_id=source_turn_id,source_episode_id=old["source_episode_id"],effective_at=old["effective_at"],expires_at=old["expires_at"])
            self._put(db,values,action="corrected",source_turn_id=source_turn_id,supersedes=old_fact_id); self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return fid

    def expire_fact(self, fact_id: str, *, source_turn_id: str | None = None) -> bool:
        db=self._write()
        try:
            row=db.execute("SELECT * FROM facts WHERE id=? AND status IN ('provisional','confirmed')",(fact_id,)).fetchone()
            if row:
                before=dict(row); now=_now(); db.execute("UPDATE facts SET status='expired',updated_at=? WHERE id=?",(now,fact_id)); self._unindex(db,fact_id)
                self._revision(db,before,fact_id=fact_id,user_id=row["user_id"],scope_key=row["scope_key"],action="expired",turn_id=source_turn_id,after={**before,"status":"expired","updated_at":now})
            self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return row is not None

    def forget_fact(self, fact_id: str) -> bool:
        db=self._write()
        try:
            row=db.execute("SELECT * FROM facts WHERE id=?",(fact_id,)).fetchone()
            if not row: self._end(db); return False
            matches=db.execute("SELECT id,value FROM facts WHERE user_id=? AND scope_key=? AND section_key=? AND key_norm=?",(row["user_id"],row["scope_key"],row["section_key"],row["key_norm"])).fetchall()
            for match in matches:
                db.execute("INSERT OR IGNORE INTO forgotten_values VALUES (?,?,?,?,?,?)",(row["user_id"],row["scope_key"],row["section_key"],row["key_norm"],_digest_value(match["value"]),_now()))
            db.execute("UPDATE extraction_jobs SET status='cancelled',input_text=NULL,patch_json=NULL,updated_at=? WHERE user_id=? AND scope_key=? AND status IN ('queued','processing')",(_now(),row["user_id"],row["scope_key"]))
            for match in matches:
                self._unindex(db,match["id"])
                db.execute("DELETE FROM revisions WHERE fact_id=?",(match["id"],))
            db.execute("DELETE FROM facts WHERE user_id=? AND scope_key=? AND section_key=? AND key_norm=?",(row["user_id"],row["scope_key"],row["section_key"],row["key_norm"]))
            self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return True

    def get_fact(self, user_id: str, fact_id: str) -> Fact | None:
        with self._connect() as db: row=db.execute("SELECT * FROM facts WHERE user_id=? AND id=?",(user_id,fact_id)).fetchone()
        return _fact(row) if row else None

    def list_facts(self, user_id: str, *, project_id: str | None = None,
                   statuses: tuple[str,...] = ("provisional","confirmed")) -> tuple[Fact,...]:
        if not statuses or any(s not in {"provisional","confirmed","superseded","expired","archived"} for s in statuses): raise InvalidMemory("invalid fact status filter")
        marks=",".join("?" for _ in statuses)
        scope_filter="project_id IS NULL" if project_id is None else "(project_id IS NULL OR project_id=?)"
        now=_now()
        params=(user_id,*statuses,*([project_id] if project_id is not None else []),now,now)
        with self._connect() as db: rows=db.execute(f"SELECT * FROM facts WHERE user_id=? AND status IN ({marks}) AND {scope_filter} AND (expires_at IS NULL OR expires_at>?) AND (effective_at IS NULL OR effective_at<=?) ORDER BY created_at,id",params).fetchall()
        return tuple(_fact(row) for row in rows)

    def _edge(self, db: sqlite3.Connection, user_id: str, project_id: str | None, source: str, target: str, relation: str, weight: float) -> str:
        scope=_scope(project_id); existing=db.execute("SELECT id FROM edges WHERE user_id=? AND scope_key=? AND from_fact_id=? AND to_fact_id=? AND relation=?",(user_id,scope,source,target,relation)).fetchone(); now=_now()
        if existing: db.execute("UPDATE edges SET weight=?,updated_at=? WHERE id=?",(weight,now,existing["id"])); return existing["id"]
        eid=str(uuid.uuid4()); db.execute("INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?,?)",(eid,user_id,project_id,scope,source,target,relation,weight,now,now)); return eid

    def add_edge(self, user_id: str, from_fact_id: str, to_fact_id: str, relation: str, *, project_id: str | None = None, weight: float = 1) -> str:
        user_id=_text(user_id,"user_id",300); relation=_text(relation,"relation",300); weight=_score(weight,"weight")
        db=self._write()
        try:
            rows=db.execute("SELECT * FROM facts WHERE id IN (?,?)",(from_fact_id,to_fact_id)).fetchall()
            if len(rows)!=2 or any(r["user_id"]!=user_id or r["project_id"]!=project_id for r in rows): raise InvalidMemory("edge endpoints must share the same user and project scope")
            eid=self._edge(db,user_id,project_id,from_fact_id,to_fact_id,relation,weight); self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return eid

    def list_edges(self, user_id: str, *, project_id: str | None = None) -> tuple[Edge,...]:
        with self._connect() as db: rows=db.execute("SELECT * FROM edges WHERE user_id=? AND scope_key=? ORDER BY created_at,id",(user_id,_scope(project_id))).fetchall()
        return tuple(Edge(r["id"],r["user_id"],r["project_id"],r["from_fact_id"],r["to_fact_id"],r["relation"],r["weight"]) for r in rows)

    def enqueue_extraction(self, user_id: str, input_text: str, *, project_id: str | None = None,
                           turn_id: str | None = None, episode_id: str | None = None, job_id: str | None = None) -> str:
        user_id=_text(user_id,"user_id",300); input_text=_text(input_text,"input_text",100_000)
        project_id=_text(project_id,"project_id",300) if project_id is not None else None
        turn_id=_text(turn_id,"turn_id",300) if turn_id else None
        episode_id=_text(episode_id,"episode_id",300) if episode_id else None
        job_id=_text(job_id,"job_id",300) if job_id else str(uuid.uuid4()); now=_now()
        db=self._write()
        try:
            if episode_id and not db.execute("SELECT 1 FROM episodes WHERE id=? AND user_id=? AND project_id IS ?",(episode_id,user_id,project_id)).fetchone(): raise InvalidMemory("episode must share extraction scope")
            old=db.execute("SELECT user_id,project_id,turn_id,episode_id FROM extraction_jobs WHERE id=?",(job_id,)).fetchone()
            if old:
                if tuple(old)!=(user_id,project_id,turn_id,episode_id): raise InvalidMemory("job_id already belongs to another request")
                self._end(db); return job_id
            db.execute("INSERT INTO extraction_jobs VALUES (?,?,?,?,?,?,?,NULL,'queued',NULL,?,?)",(job_id,user_id,project_id,_scope(project_id),turn_id,episode_id,input_text,now,now)); self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return job_id

    @staticmethod
    def validate_patch(patch: Mapping[str,Any]) -> tuple[list[dict[str,Any]],list[dict[str,Any]]]:
        if not isinstance(patch,Mapping) or set(patch)-{"facts","edges"}: raise InvalidMemory("patch accepts only facts and edges")
        facts,edges=patch.get("facts",[]),patch.get("edges",[])
        if not isinstance(facts,list) or not isinstance(edges,list) or len(facts)>100 or len(edges)>200: raise InvalidMemory("facts and edges must be bounded lists")
        allowed={"section","key","value","confidence","salience","stability","is_durable","sensitivity","allow_export","effective_at","expires_at"}
        clean=[]
        for item in facts:
            if not isinstance(item,Mapping) or set(item)-allowed or not {"section","key","value"}<=set(item): raise InvalidMemory("invalid extraction fact fields")
            one={"section":_text(item["section"],"section",300),"key":_text(item["key"],"key",300),"value":_text(item["value"],"value",20_000),"confidence":_score(item.get("confidence",.5),"confidence"),"salience":_score(item.get("salience",.5),"salience"),"stability":item.get("stability",1),"is_durable":item.get("is_durable",False),"sensitivity":item.get("sensitivity","personal"),"allow_export":item.get("allow_export",False),"effective_at":item.get("effective_at"),"expires_at":item.get("expires_at")}
            if isinstance(one["stability"],bool) or not isinstance(one["stability"],(int,float)) or not math.isfinite(one["stability"]) or one["stability"]<0: raise InvalidMemory("stability must be finite and nonnegative")
            if not isinstance(one["is_durable"],bool) or not isinstance(one["allow_export"],bool): raise InvalidMemory("durable and export flags must be boolean")
            if one["allow_export"]: raise InvalidMemory("extracted facts cannot grant export permission")
            if one["sensitivity"] not in {"public","personal","sensitive"}: raise InvalidMemory("invalid sensitivity")
            _time(one["effective_at"],"effective_at"); _time(one["expires_at"],"expires_at"); clean.append(one)
        edge_allowed={"from_section","from_key","to_section","to_key","relation","weight"}; clean_edges=[]
        for item in edges:
            if not isinstance(item,Mapping) or set(item)-edge_allowed or not {"from_section","from_key","to_section","to_key","relation"}<=set(item): raise InvalidMemory("invalid extraction edge fields")
            clean_edges.append({"from_section":_text(item["from_section"],"from_section",300),"from_key":_text(item["from_key"],"from_key",300),"to_section":_text(item["to_section"],"to_section",300),"to_key":_text(item["to_key"],"to_key",300),"relation":_text(item["relation"],"relation",300),"weight":_score(item.get("weight",1),"weight")})
        return clean,clean_edges

    def claim_extraction_jobs(self, *, limit: int = 10) -> tuple[dict[str,Any],...]:
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=100: raise InvalidMemory("limit must be between 1 and 100")
        db=self._write()
        try:
            rows=db.execute("SELECT * FROM extraction_jobs WHERE status='queued' ORDER BY created_at,id LIMIT ?",(limit,)).fetchall(); now=_now()
            for row in rows: db.execute("UPDATE extraction_jobs SET status='processing',updated_at=? WHERE id=? AND status='queued'",(now,row["id"]))
            self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return tuple(dict(r)|{"status":"processing"} for r in rows)

    def requeue_stale_extractions(self, *, before: str | datetime) -> int:
        """Return abandoned processing work to the queue after an explicit timeout."""
        cutoff=_time(before,"before")
        if cutoff is None: raise InvalidMemory("before timestamp is required")
        db=self._write()
        try:
            changed=db.execute("UPDATE extraction_jobs SET status='queued',updated_at=? WHERE status='processing' AND updated_at<?",(_now(),cutoff)).rowcount
            self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return changed

    def finish_extraction(self, job_id: str, *, failed: bool = False, error_code: str = "extraction_failed") -> str:
        status="failed" if failed else "no_facts"; error_code=_text(error_code,"error_code",100) if failed else None
        if error_code and not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}",error_code): raise InvalidMemory("error_code must be a short lowercase code")
        db=self._write()
        try:
            row=db.execute("SELECT status FROM extraction_jobs WHERE id=?",(job_id,)).fetchone()
            if not row or row["status"] not in {"queued","processing"}: raise JobNotRunnable("extraction job is no longer runnable")
            db.execute("UPDATE extraction_jobs SET status=?,error_code=?,input_text=NULL,updated_at=? WHERE id=?",(status,error_code,_now(),job_id)); self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return status

    def apply_extraction_patch(self, job_id: str, patch: Mapping[str,Any]) -> tuple[str,...]:
        facts,edges=self.validate_patch(patch); db=self._write()
        try:
            job=db.execute("SELECT * FROM extraction_jobs WHERE id=?",(job_id,)).fetchone()
            if not job or job["status"] not in {"queued","processing"}: raise JobNotRunnable("extraction job is no longer runnable")
            now=_now(); made=[]; mapped={}
            for item in facts:
                tombstone=db.execute("SELECT 1 FROM forgotten_values WHERE user_id=? AND scope_key=? AND section_key=? AND key_norm=? AND value_hash=?",(job["user_id"],job["scope_key"],item["section"].casefold(),item["key"].casefold(),_digest_value(item["value"]))).fetchone()
                if tombstone: continue
                fid=str(uuid.uuid4()); values=self._values(fact_id=fid,user_id=job["user_id"],project_id=job["project_id"],section=item["section"],key=item["key"],value=item["value"],status="provisional",confidence=item["confidence"],salience=item["salience"],stability=item["stability"],is_durable=item["is_durable"],sensitivity=item["sensitivity"],allow_export=item["allow_export"],source_turn_id=job["turn_id"],source_episode_id=job["episode_id"],effective_at=item["effective_at"],expires_at=item["expires_at"],created_at=now,updated_at=now)
                self._put(db,values,action="extracted",source_turn_id=job["turn_id"]); made.append(fid); mapped[(item["section"].casefold(),item["key"].casefold())]=fid
            for edge in edges:
                ids=[]
                for prefix in ("from","to"):
                    pair=(edge[prefix+"_section"].casefold(),edge[prefix+"_key"].casefold()); fid=mapped.get(pair)
                    if not fid:
                        row=db.execute("SELECT id FROM facts WHERE user_id=? AND scope_key=? AND section_key=? AND key_norm=? AND status IN ('confirmed','provisional') ORDER BY status='confirmed' DESC,created_at DESC LIMIT 1",(job["user_id"],job["scope_key"],*pair)).fetchone(); fid=row["id"] if row else None
                    ids.append(fid)
                if all(ids) and ids[0]!=ids[1]: self._edge(db,job["user_id"],job["project_id"],ids[0],ids[1],edge["relation"],edge["weight"])
            done_status="no_facts" if not facts and not edges else "applied"
            db.execute("UPDATE extraction_jobs SET status=?,input_text=NULL,patch_json=?,updated_at=? WHERE id=?",(done_status,json.dumps({"fact_count":len(made),"edge_count":len(edges)}),_now(),job_id)); self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return tuple(made)

    def fact_revisions(self, fact_id: str, *, user_id: str) -> tuple[dict[str,Any],...]:
        with self._connect() as db: rows=db.execute("SELECT * FROM revisions WHERE fact_id=? AND user_id=? ORDER BY id",(fact_id,user_id)).fetchall()
        return tuple({**dict(r),"before":json.loads(r["before_json"]) if r["before_json"] else None,"after":json.loads(r["after_json"]) if r["after_json"] else None} for r in rows)

    def rebuild_index(self) -> int:
        db=self._write()
        try:
            db.execute("DELETE FROM facts_fts"); db.execute("INSERT INTO facts_fts(fact_id,user_id,scope_key,section,fact_key,value) SELECT id,user_id,scope_key,section,fact_key,value FROM facts WHERE status IN ('provisional','confirmed')")
            count=db.execute("SELECT count(*) FROM facts WHERE status IN ('provisional','confirmed')").fetchone()[0]; self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return count

    def read_profile(self, user_id: str = "default") -> str:
        path=self._profile_for(_text(user_id,"user_id",300))
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    def read_persona(self) -> str: return self.persona_path.read_text(encoding="utf-8")

    def recall(self, user_id: str, query: str, *, project_id: str | None = None, limit: int = 10) -> Recall:
        user_id=_text(user_id,"user_id",300)
        if not isinstance(query,str): raise InvalidMemory("query must be text")
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=100: raise InvalidMemory("limit must be between 1 and 100")
        project_id=_text(project_id,"project_id",300) if project_id is not None else None
        terms=list(dict.fromkeys(re.findall(r"[\w]+",query.casefold(),flags=re.UNICODE)))[:40]
        overrides=[]; section=""
        for line in self.read_profile(user_id).splitlines():
            heading=re.match(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$",line)
            if heading: section=heading.group(1).strip().casefold().replace(" ","_"); continue
            item=re.match(r"^\s*[-*]\s+\*\*(.+?)\*\*\s*:\s*(.*?)\s*$",line)
            if item and item[2] and section in {"preferences","preference","user_preferences","communication_preferences"}: overrides.append((section,item[1].strip(),item[2].strip()))
        visible_overrides=tuple(overrides)
        if not terms: return Recall((),visible_overrides)
        match=" OR ".join('"'+term.replace('"','""')+'"*' for term in terms)
        scope_filter="f.scope_key='global'" if project_id is None else "f.scope_key IN ('global',?)"
        params=(match,user_id,*([_scope(project_id)] if project_id is not None else []),_now(),limit*5)
        with self._connect() as db:
            rows=db.execute(f"SELECT f.*,bm25(facts_fts) rank FROM facts_fts JOIN facts f ON f.id=facts_fts.fact_id WHERE facts_fts MATCH ? AND f.user_id=? AND {scope_filter} AND f.status IN ('provisional','confirmed') AND (f.expires_at IS NULL OR f.expires_at>?) ORDER BY rank,f.created_at DESC LIMIT ?",params).fetchall()
        override_keys={(s,k.casefold()) for s,k,_ in overrides}
        found=[]
        for row in rows:
            item=_fact(row)
            if (item.section.casefold(),item.key.casefold()) in override_keys: continue
            found.append(item)
            if len(found)>=limit: break
        return Recall(tuple(found),visible_overrides)

    def backup_to(self, destination: str | Path) -> Path:
        path=Path(destination).resolve()
        if path.exists(): raise FileExistsError("Backup destination already exists")
        path.parent.mkdir(parents=True,exist_ok=True); source=self._connect(); target=sqlite3.connect(path)
        try: source.backup(target)
        finally: target.close(); source.close()
        return path

    @staticmethod
    def backup_database(database: str | Path, destination: str | Path) -> Path:
        """Back up an existing SQLite file before schema initialization or writes."""
        source_path=Path(database).resolve(); backup_path=Path(destination).resolve()
        if not source_path.is_file(): raise InvalidMemory("Existing migration target is not a database file")
        if backup_path.exists(): raise FileExistsError("Backup destination already exists")
        backup_path.parent.mkdir(parents=True,exist_ok=True)
        source=sqlite3.connect(source_path.as_uri()+"?mode=ro",uri=True,timeout=30)
        destination_db=sqlite3.connect(backup_path)
        try: source.backup(destination_db)
        except sqlite3.DatabaseError:
            destination_db.close(); backup_path.unlink(missing_ok=True)
            raise InvalidMemory("Existing migration target is not a readable SQLite database") from None
        finally:
            source.close()
        destination_db.close()
        return backup_path

    def _import_snapshot(self,user_id:str,snapshot:Mapping[str,Any],*,source_key:str,digest:str)->tuple[bool,int,int,int]:
        db=self._write()
        try:
            if db.execute("SELECT 1 FROM migration_imports WHERE source_key=? AND digest=? AND user_id=?",(source_key,digest,user_id)).fetchone(): self._end(db); return False,0,0,0
            tag=source_key[:10]; mapping={}; fact_count=edge_count=episode_count=0
            episode_ids=set()
            for item in snapshot["episodes"]:
                db.execute("INSERT OR IGNORE INTO episodes VALUES (?,?,?,?,?,?,?,?,?)",(item["event_id"],user_id,None,None,_time(item.get("timestamp"),"timestamp") or _now(),item["raw_text"],item["emotion"],item["salience"],json.dumps(item["triggers"])))
                episode_ids.add(item["event_id"]); episode_count+=1
            for node in snapshot["nodes"]:
                legacy=node["node_id"]; fid=str(uuid.uuid5(uuid.NAMESPACE_URL,f"sadaf-import:{user_id}:{tag}:{legacy}"))
                legacy_section_key=node["section"].casefold(); legacy_key=node["key"].casefold()
                forgotten=db.execute("SELECT 1 FROM forgotten_values WHERE user_id=? AND scope_key='global' AND section_key=? AND key_norm=? AND value_hash=?",(user_id,legacy_section_key,legacy_key,_digest_value(node["value"]))).fetchone()
                if forgotten: continue
                old_state=node["status"]; state="archived" if old_state=="archived" else "provisional" if old_state=="provisional" else "confirmed"
                source_episode=node.get("source_episode_id") if node.get("source_episode_id") in episode_ids else None
                values=self._values(fact_id=fid,user_id=user_id,project_id=None,section=node["section"],key=node["key"],value=node["value"],status=state,confidence=node["confidence"],salience=node["salience"],stability=node["stability"],is_durable=node["is_durable"],sensitivity=node["sensitivity"],allow_export=node["allow_export"],source_turn_id=None,source_episode_id=source_episode,effective_at=None,expires_at=None,legacy_node_id=legacy,created_at=node["created_at"],updated_at=node["updated_at"])
                self._put(db,values,action="legacy_import"); mapping[legacy]=fid; fact_count+=1
            for index,note in enumerate(snapshot["sessions"]):
                eid=str(uuid.uuid5(uuid.NAMESPACE_URL,f"sadaf-session:{user_id}:{tag}:{index}:{note}")); at=_now(); body=note
                match=re.match(r"^\[([^]]+)\]\s*(.*)$",note)
                if match:
                    try: at=_time(match[1],"session timestamp") or at
                    except InvalidMemory: pass
                    body=match[2]
                db.execute("INSERT OR IGNORE INTO episodes VALUES (?,?,?,?,?,?,?,?,?)",(eid,user_id,None,None,at,body,None,.5,"[]")); episode_count+=1
            for edge in snapshot["edges"]:
                a=mapping.get(edge["from_node"]); b=mapping.get(edge["to_node"])
                if a and b and a!=b: self._edge(db,user_id,None,a,b,edge["relation"],edge["weight"]); edge_count+=1
            db.execute("INSERT INTO migration_imports VALUES (?,?,?,?,?,?,?)",(source_key,digest,user_id,_now(),fact_count,edge_count,episode_count)); self._end(db)
        except BaseException as exc: self._end(db,exc); raise
        return True,fact_count,edge_count,episode_count
