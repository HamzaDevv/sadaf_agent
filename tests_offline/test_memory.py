from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import os
import subprocess
import sys

import pytest

from sadaf.memory import InvalidMemory, JobNotRunnable, MemoryStore
from sadaf.migration import migrate_legacy
from sadaf.settings import load_settings


@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path / "data" / "memory.sqlite3")


def test_episode_fact_evidence_revision_restart_and_edges(store, tmp_path):
    episode=store.add_episode("user-a","Synthetic fixture turn",turn_id="turn-a",triggers=("offline",))
    first=store.record_fact("user-a","identity","display_name","Fixture User",status="confirmed",
        confidence=.98,is_durable=True,source_turn_id="turn-a",source_episode_id=episode.id)
    second=store.record_fact("user-a","career","role","Synthetic Tester",source_turn_id="turn-a",source_episode_id=episode.id)
    edge=store.add_edge("user-a",first,second,"has_role")
    assert store.get_fact("user-a",first).source_episode_id==episode.id
    assert store.get_episode("user-a",episode.id).turn_id=="turn-a"
    assert store.list_edges("user-a")[0].id==edge
    assert store.fact_revisions(first,user_id="user-a")[0]["action"]=="record"
    reopened=MemoryStore(store.database)
    assert reopened.get_fact("user-a",second).value=="Synthetic Tester"
    assert reopened.list_edges("user-a")[0].relation=="has_role"


def test_episode_ids_are_scoped_to_their_user(store):
    a=store.add_episode("user-a","evidence A",episode_id="same-event")
    b=store.add_episode("user-b","evidence B",episode_id="same-event")
    fa=store.record_fact("user-a","x","a","A",source_episode_id=a.id)
    fb=store.record_fact("user-b","x","b","B",source_episode_id=b.id)
    assert store.get_episode("user-a","same-event").raw_text=="evidence A"
    assert store.get_episode("user-b","same-event").raw_text=="evidence B"
    assert store.get_fact("user-a",fa).source_episode_id==store.get_fact("user-b",fb).source_episode_id


def test_from_settings_initializes_only_the_explicit_new_data_root(tmp_path):
    settings=load_settings(root=tmp_path,environ={},read_dotenv=False)
    assert not settings.data_dir.exists()
    store=MemoryStore.from_settings(settings)
    assert store.database==settings.data_dir/"memory.sqlite3"
    assert settings.profile_path.parent.joinpath("default-37a8eec1.md").is_file()
    assert settings.persona_path.is_file()
    assert not (tmp_path/"memories").exists()


def test_provisional_conflict_does_not_overwrite_confirmed_and_correction_is_explicit(store):
    confirmed=store.record_fact("u","preferences","language","English",status="confirmed",is_durable=True)
    disputed=store.record_fact("u","preferences","language","French",status="provisional",confidence=.55)
    assert store.get_fact("u",confirmed).status=="confirmed"
    assert store.get_fact("u",disputed).status=="provisional"
    replacement=store.correct_fact(confirmed,"Hindi",source_turn_id="turn-correction")
    assert store.get_fact("u",confirmed).status=="superseded"
    assert store.get_fact("u",disputed).status=="superseded"
    assert store.get_fact("u",replacement).status=="confirmed"
    revisions=store.fact_revisions(confirmed,user_id="u")
    assert revisions[-1]["action"]=="superseded"
    assert revisions[-1]["source_turn_id"]=="turn-correction"
    assert [fact.value for fact in store.recall("u","language").facts]==["Hindi"]


def test_durable_facts_are_not_decayed_and_expiry_is_read_only(store):
    durable=store.record_fact("u","identity","name","Fixture",status="confirmed",is_durable=True)
    expired=store.record_fact("u","status","temporary","Fixture window",status="confirmed",
        expires_at=datetime.now(timezone.utc)-timedelta(days=1))
    assert [f.id for f in store.list_facts("u")] == [durable]
    assert store.get_fact("u",expired).status=="confirmed"  # reads do not transition state
    assert store.expire_fact(durable)
    assert store.get_fact("u",durable).status=="expired"
    assert not store.recall("u","Fixture").facts


def test_explicit_profile_preferences_override_extracted_values(store):
    store.profile_path.write_text("# Profile\n\n## Preferences\n- **reply_style**: concise\n",encoding="utf-8")
    store.record_fact("default","preferences","reply_style","detailed",status="confirmed",is_durable=True)
    store.record_fact("default","preferences","other","warm",status="confirmed")
    result=store.recall("default","reply style other")
    assert [(section,key,value) for section,key,value in result.profile_overrides]==[("preferences","reply_style","concise")]
    assert [fact.key for fact in result.facts]==["other"]
    store.persona_path.write_text("# Assistant style\n\nUse clear language.\n",encoding="utf-8")
    assert "clear language" in store.read_persona()


def test_scope_isolation_and_global_context_overlay(store):
    global_id=store.record_fact("u","identity","alias","Global fixture",status="confirmed")
    p1=store.record_fact("u","project","branch","project one",project_id="p1",status="confirmed")
    store.record_fact("u","project","branch","project two",project_id="p2",status="confirmed")
    assert {f.id for f in store.recall("u","fixture branch",project_id="p1").facts}=={global_id,p1}
    assert {f.id for f in store.list_facts("u",project_id="p1")}=={global_id,p1}
    assert {f.id for f in store.list_facts("u")}=={global_id}
    assert not store.recall("other-user","fixture branch",project_id="p1").facts


def test_profile_preferences_are_separated_by_user(store):
    store.profile_path.write_text("# Profile\n\n## Preferences\n- **reply_style**: concise\n",encoding="utf-8")
    other=store._profile_for("other-user")
    other.parent.mkdir(parents=True,exist_ok=True)
    other.write_text("# Profile\n\n## Preferences\n- **reply_style**: detailed\n",encoding="utf-8")
    assert store.recall("default","reply style").profile_overrides[0][2]=="concise"
    assert store.recall("other-user","reply style").profile_overrides[0][2]=="detailed"
    assert not store.recall("unknown-user","reply style").profile_overrides


def test_per_user_profile_symlink_is_rejected(store,tmp_path):
    candidate=store._profile_for("untrusted-user")
    candidate.parent.mkdir(parents=True,exist_ok=True)
    candidate.symlink_to(tmp_path/"outside-profile.md")
    with pytest.raises(InvalidMemory,match="symlink"):
        store.read_profile("untrusted-user")


def test_profile_preferences_are_separated_by_user(store):
    store.profile_path.write_text("# Profile\n\n## Preferences\n- **reply_style**: concise\n",encoding="utf-8")
    other=store._profile_for("other-user")
    other.parent.mkdir(parents=True,exist_ok=True)
    other.write_text("# Profile\n\n## Preferences\n- **reply_style**: detailed\n",encoding="utf-8")
    store.record_fact("u","preferences","reply_style","verbose",status="confirmed")
    assert store.recall("default","reply style").profile_overrides[0][2]=="concise"
    assert store.recall("other-user","reply style").profile_overrides[0][2]=="detailed"
    assert not store.recall("unknown-user","reply style").profile_overrides


def test_recall_is_lexical_rebuildable_and_does_not_write(store):
    fact=store.record_fact("u","projects","favorite_color","blue fixture",status="confirmed")
    before=store.database.stat().st_mtime_ns
    assert store.recall("u","favorite colo").facts[0].id==fact
    assert store.database.stat().st_mtime_ns==before
    assert store.rebuild_index()==1
    assert store.recall("u","favorite color").facts[0].id==fact


def test_edges_cannot_cross_user_or_project_scopes(store):
    a=store.record_fact("u","x","a","A",status="confirmed")
    b=store.record_fact("u","x","b","B",status="confirmed",project_id="p")
    with pytest.raises(InvalidMemory): store.add_edge("u",a,b,"bad")
    other=store.record_fact("other","x","b","B",status="confirmed")
    with pytest.raises(InvalidMemory): store.add_edge("u",a,other,"bad")


def test_extraction_outbox_evidence_validation_and_no_facts_vs_failure(store):
    ep=store.add_episode("u","Synthetic evidence",turn_id="turn-e")
    job=store.enqueue_extraction("u","synthetic request",turn_id="turn-e",episode_id=ep.id,job_id="job-e")
    claimed=store.claim_extraction_jobs()
    assert claimed[0]["id"]==job and claimed[0]["status"]=="processing"
    ids=store.apply_extraction_patch(job,{"facts":[{"section":"work","key":"tool","value":"offline fixture","confidence":.7}],"edges":[]})
    fact=store.get_fact("u",ids[0])
    assert fact.status=="provisional" and fact.source_turn_id=="turn-e" and fact.source_episode_id==ep.id
    no_facts=store.enqueue_extraction("u","nothing new",job_id="job-none")
    assert store.finish_extraction(no_facts)=="no_facts"
    failed=store.enqueue_extraction("u","service failure",job_id="job-failed")
    assert store.finish_extraction(failed,failed=True,error_code="timeout")=="failed"
    with sqlite3.connect(store.database) as db:
        statuses=dict(db.execute("SELECT id,status FROM extraction_jobs"))
    assert statuses=={"job-e":"applied","job-none":"no_facts","job-failed":"failed"}


def test_extraction_patch_adds_valid_edges_in_same_transaction(store):
    job=store.enqueue_extraction("u","synthetic relation fixture")
    created=store.apply_extraction_patch(job,{"facts":[{"section":"work","key":"tool","value":"SQLite"},{"section":"work","key":"purpose","value":"durable storage"}],"edges":[{"from_section":"work","from_key":"tool","to_section":"work","to_key":"purpose","relation":"supports","weight":.8}]})
    assert len(created)==2
    edges=store.list_edges("u")
    assert len(edges)==1 and edges[0].from_fact_id==created[0] and edges[0].to_fact_id==created[1]


@pytest.mark.parametrize("patch",[
    {"facts":[{"section":"x","key":"y","value":"z","status":"confirmed"}]},
    {"facts":[{"section":"x","key":"y","value":"z","allow_export":True}]},
    {"facts":[{"section":"x","key":"y","value":"z","confidence":2}]},
    {"facts":"not a list"},
    {"unknown":[]},
])
def test_invalid_extraction_patches_never_change_job_or_facts(store,patch):
    job=store.enqueue_extraction("u","synthetic input")
    with pytest.raises(InvalidMemory): store.apply_extraction_patch(job,patch)
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT status FROM extraction_jobs WHERE id=?",(job,)).fetchone()[0]=="queued"
        assert db.execute("SELECT count(*) FROM facts").fetchone()[0]==0


def test_forget_removes_index_revisions_edges_and_cancels_queued_work(store):
    a=store.record_fact("u","plans","topic","private fixture token",status="confirmed")
    b=store.record_fact("u","plans","related","another fixture",status="confirmed")
    store.add_edge("u",a,b,"related_to")
    job=store.enqueue_extraction("u","input contains private fixture token")
    assert store.forget_fact(a)
    assert store.get_fact("u",a) is None
    assert not store.recall("u","private").facts
    assert store.fact_revisions(a,user_id="u")==()
    assert store.list_edges("u")==()
    with sqlite3.connect(store.database) as db:
        status,input_text=db.execute("SELECT status,input_text FROM extraction_jobs WHERE id=?",(job,)).fetchone()
    assert status=="cancelled" and input_text is None
    with pytest.raises(JobNotRunnable): store.apply_extraction_patch(job,{"facts":[{"section":"plans","key":"topic","value":"private fixture token"}]})
    later=store.enqueue_extraction("u","new synthetic input")
    assert store.apply_extraction_patch(later,{"facts":[{"section":"plans","key":"topic","value":"private fixture token"}]})==()
    assert not store.recall("u","private").facts
    with pytest.raises(InvalidMemory,match="explicit confirmation"):
        store.record_fact("u","plans","topic","private fixture token")
    restored=store.record_fact("u","plans","topic","private fixture token",status="confirmed",source_turn_id="explicit-restore")
    assert store.get_fact("u",restored).status=="confirmed"
    assert store.recall("u","private").facts[0].id==restored


def test_outbox_job_id_is_idempotent_but_cannot_change_scope(store):
    job=store.enqueue_extraction("u","same synthetic input",turn_id="t",job_id="stable")
    assert store.enqueue_extraction("u","different payload but same logical id",turn_id="t",job_id="stable")==job
    with pytest.raises(InvalidMemory): store.enqueue_extraction("u","x",turn_id="other",job_id="stable")


def test_stale_processing_jobs_can_be_recovered_after_restart(store):
    job=store.enqueue_extraction("u","synthetic queue item")
    store.claim_extraction_jobs()
    assert store.requeue_stale_extractions(before=datetime.now(timezone.utc)+timedelta(seconds=1))==1
    recovered=MemoryStore(store.database).claim_extraction_jobs()
    assert recovered[0]["id"]==job and recovered[0]["input_text"]=="synthetic queue item"


def test_forgetting_a_key_removes_all_its_conflicts(store):
    confirmed=store.record_fact("u","preferences","language","English fixture",status="confirmed")
    provisional=store.record_fact("u","preferences","language","French fixture",status="provisional")
    assert store.forget_fact(provisional)
    assert store.get_fact("u",confirmed) is None
    assert store.get_fact("u",provisional) is None
    assert not store.recall("u","English").facts


def test_concurrent_writes_across_store_instances_are_transactional(tmp_path):
    path=tmp_path/"concurrent.sqlite3"
    MemoryStore(path)
    def write(index):
        return MemoryStore(path).record_fact("u","concurrency",f"key-{index}",f"synthetic value {index}",status="confirmed")
    with ThreadPoolExecutor(max_workers=8) as pool: ids=list(pool.map(write,range(32)))
    reopened=MemoryStore(path)
    assert len(set(ids))==32
    assert len(reopened.list_facts("u"))==32
    assert len(reopened.recall("u","synthetic value").facts)==10


def fixture_tree(path: Path):
    path.mkdir()
    episode={"event_id":"event-fixture","timestamp":"2026-01-02T03:04:05+00:00","raw_text":"synthetic source evidence","emotion":"calm","salience":.6,"contextual_triggers":["fixture"]}
    graph={"nodes":{"fixture:a":{"node_id":"fixture:a","section":"work","key":"role","value":"tester","status":"active","source_episode_id":"event-fixture","confidence":.9,"salience":.8,"stability":2,"created_at":"2025-01-01T00:00:00+00:00"},"fixture:b":{"node_id":"fixture:b","section":"work","key":"tool","value":"sqlite","status":"provisional"}},"edges":[{"from_node":"fixture:a","to_node":"fixture:b","relation":"uses","weight":.7}],"sessions":["[2026-02-03 12:30] synthetic session note"]}
    (path/"graph.json").write_text(json.dumps(graph),encoding="utf-8")
    (path/"archive.json").write_text(json.dumps({"nodes":{"fixture:old":{"node_id":"fixture:old","section":"old","key":"fact","value":"archived synthetic value","status":"archived"}}}),encoding="utf-8")
    (path/"episodes.json").write_text(json.dumps({"episodes":[episode]}),encoding="utf-8")


def test_migration_dry_run_apply_backup_and_repeat_are_safe(tmp_path):
    source=tmp_path/"synthetic-copy"; fixture_tree(source)
    target=tmp_path/"target"/"memory.sqlite3"
    plan=migrate_legacy(source,target,legacy_root=tmp_path/"real-memories")
    assert not plan.applied and (plan.facts,plan.edges,plan.episodes)==(3,1,2)
    assert not target.parent.exists()
    applied=migrate_legacy(source,target,apply=True,legacy_root=tmp_path/"real-memories")
    assert applied.applied and not applied.already_imported and applied.backup is None
    db=MemoryStore(target)
    assert len(db.list_facts("default"))==2
    assert len(db.list_facts("default",statuses=("archived",)))==1
    imported=db.list_facts("default")
    legacy_role=next(f for f in imported if f.key=="role")
    assert legacy_role.source_episode_id=="event-fixture"
    assert db.get_episode("default","event-fixture").raw_text=="synthetic source evidence"
    repeat=migrate_legacy(source,target,apply=True,legacy_root=tmp_path/"real-memories")
    assert repeat.already_imported and (repeat.facts,repeat.edges,repeat.episodes)==(0,0,0)
    assert len(db.list_facts("default",statuses=("confirmed","provisional","archived")))==3
    separate_user=migrate_legacy(source,target,user_id="second-user",apply=True,legacy_root=tmp_path/"real-memories")
    assert separate_user.applied
    assert MemoryStore(target).get_episode("second-user","event-fixture").raw_text=="synthetic source evidence"


def test_existing_target_is_backed_up_before_import_mutates_it(tmp_path):
    target=tmp_path/"target.sqlite3"; original=MemoryStore(target)
    original.record_fact("u","fixture","before","original database state",status="confirmed")
    with sqlite3.connect(target) as db: before=db.execute("SELECT count(*) FROM facts").fetchone()[0]
    source=tmp_path/"copy"; fixture_tree(source)
    report=migrate_legacy(source,target,apply=True,legacy_root=tmp_path/"real-memories")
    assert report.backup and Path(report.backup).is_file()
    with sqlite3.connect(report.backup) as backup: assert backup.execute("SELECT count(*) FROM facts").fetchone()[0]==before
    assert len(MemoryStore(target).list_facts("default",statuses=("confirmed","provisional","archived")))==3


def test_migration_rejects_real_legacy_overlap_and_malformed_fixture(tmp_path):
    real=tmp_path/"memories"; fixture_tree(real)
    target=tmp_path/"target.sqlite3"
    with pytest.raises(InvalidMemory,match="legacy memory"): migrate_legacy(real,target,legacy_root=real)
    assert not target.exists()
    bad=tmp_path/"bad"; bad.mkdir(); (bad/"graph.json").write_text("{bad",encoding="utf-8")
    with pytest.raises(InvalidMemory,match="invalid"): migrate_legacy(bad,target,legacy_root=real)
    assert not target.exists()


def test_migration_dry_run_validates_fields_needed_by_apply(tmp_path):
    source=tmp_path/"bad-time"; fixture_tree(source)
    data=json.loads((source/"episodes.json").read_text())
    data["episodes"][0]["timestamp"]="not a timestamp"
    (source/"episodes.json").write_text(json.dumps(data))
    with pytest.raises(InvalidMemory,match="ISO-8601"):
        migrate_legacy(source,tmp_path/"target.sqlite3",legacy_root=tmp_path/"memories")
    assert not (tmp_path/"target.sqlite3").exists()


def test_migration_command_defaults_to_dry_run(tmp_path):
    source=tmp_path/"synthetic-copy"; fixture_tree(source)
    target=tmp_path/"import.sqlite3"
    root=Path(__file__).resolve().parents[1]
    env={"PATH":os.environ.get("PATH",""),"PYTHONPATH":str(root),"PYTHONNOUSERSITE":"1","PYTHONDONTWRITEBYTECODE":"1"}
    result=subprocess.run([sys.executable,str(root/"scripts/migrate_memory.py"),"--source",str(source),"--target",str(target)],
        cwd=tmp_path,env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)["mode"]=="dry-run"
    assert not target.exists()
    applied=subprocess.run([sys.executable,str(root/"scripts/migrate_memory.py"),"--source",str(source),"--target",str(target),"--apply"],
        cwd=tmp_path,env=env,capture_output=True,text=True,timeout=10)
    assert applied.returncode==0,applied.stderr
    assert json.loads(applied.stdout)["mode"]=="applied"
    assert MemoryStore(target).list_facts("default")
