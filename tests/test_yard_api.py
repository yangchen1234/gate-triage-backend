"""Durable yard contract, concurrency, recurrence, provenance and failure recovery."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from gate_triage.config import Settings
from gate_triage.yard_store import YardStore
from main import create_app

HEADERS = {'X-Yard-Request': '1'}


@pytest.fixture
def settings(tmp_path): return Settings(yard_database_path=tmp_path/'yard.sqlite3')


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        assert c.post('/api/yard/session', headers=HEADERS).status_code == 200
        yield c


def snapshot(c, port='la'): return c.get(f'/api/yard/ports/{port}/snapshot')

def command(c, state, event, port='la', key=None):
    etag = state.headers['etag'] if hasattr(state, 'headers') else state
    return c.post(f'/api/yard/ports/{port}/commands', json=event, headers={**HEADERS, 'If-Match': etag, 'Idempotency-Key': key or str(uuid4())})


def advance(c, state, event, port='la'):
    r = command(c, state, event, port)
    assert r.status_code == 200, r.text
    return r


def resolve(c, state, cid, issue, scenario='routine', port='la'):
    state = advance(c, state, dict(type='review', containerId=cid, issue=issue, scenario=scenario, choice='accepted', note='SIMULATED handoff'), port)
    key = next(j['key'] for j in state.json()['run']['jobs'] if j['containerId'] == cid and j['issue'] == issue and j['stage'] != 'resolved')
    state = advance(c, state, dict(type='start', key=key), port)
    state = advance(c, state, dict(type='complete_work', key=key, note='SIMULATED completed check'), port)
    return advance(c, state, dict(type='verify', key=key, evidence='SIMULATED verified reference', confirmed=True), port)


def gate(cid, **changes): return dict(type='gate_out', containerId=cid, scenario='routine', evidence='SIMULATED gate-out G-1', clearanceConfirmed=True, exitConfirmed=True, **changes)
def active(s): return [c for c in s.json()['catalog'] if c['yardStatus']=='in-yard']


def test_seed_profiles_auth_conditional_reads_and_current_inventory(client):
    la, rt = snapshot(client), snapshot(client,'rotterdam')
    assert len(la.json()['blocks']) == 12 and len(active(la)) == 1780
    assert len(rt.json()['blocks']) == 8 and len(active(rt)) == 1142
    assert la.json()['persisted'] is True and la.json()['agentEnabled'] is False
    cached = client.get('/api/yard/ports/la/snapshot', headers={'If-None-Match': la.headers['etag']})
    assert cached.status_code == 304 and not cached.content
    assert la.headers['cache-control'] == 'no-store'
    for company in ('Maersk', 'MAEU', ' ma-eu '):
        r = client.get('/api/yard/ports/la/containers',params={'company':company,'limit':200})
        assert r.status_code == 200 and r.json()['total'] == 343
    c = la.json()['catalog'][0]
    assert client.get('/api/yard/ports/la/containers',params={'container_id':c['id'].lower().replace('simu','simu-')}).json()['total']==1
    assert client.get('/api/yard/ports/la/containers',params={'container_id':'!!!'}).json()['total']==0
    assert client.get('/api/yard/ports/la/containers',params={'limit':201}).status_code==422
    assert snapshot(client,'unknown').status_code == 422
    assert client.get('/api/yard/ports/rotterdam/containers/'+c['id']).status_code == 404


def test_acceptance_is_not_completion_and_verified_normal_stock_does_not_leave(client):
    s=snapshot(client); c=next(c for c in active(s) if c['issue']=='weight')
    r=advance(client,s,dict(type='review',containerId=c['id'],issue='weight',scenario='routine',choice='accepted',note='SIM handoff'))
    j=r.json()['run']['jobs'][0]
    assert j['stage']=='queued' and len(active(r))==1780
    assert next(x for x in active(r) if x['id']==c['id'])['issue']=='weight'
    assert command(client,r,dict(type='verify',key=j['key'],confirmed=True,evidence='SIM verified')).status_code==409
    r=advance(client,r,dict(type='start',key=j['key']))
    assert command(client,r,dict(type='complete_work',key=j['key'],note='  ')).status_code==422
    r=advance(client,r,dict(type='complete_work',key=j['key'],note='SIM work completed'))
    assert command(client,r,dict(type='verify',key=j['key'],confirmed=False,evidence='SIM verified')).status_code==422
    assert snapshot(client).json()['run']['resolutions']==[]
    r=advance(client,r,dict(type='verify',key=j['key'],confirmed=True,evidence='SIM authority verification'))
    fixed=next(x for x in active(r) if x['id']==c['id'])
    assert fixed['issue']=='clear' and fixed['declared']==fixed['weight']
    assert len(active(r))==1780
    original=client.get('/api/yard/ports/la/containers/'+c['id']).json()['originalObservation']
    assert original['issue']=='weight' and original['declared']!=original['weight']


def test_gate_out_requires_two_confirmations_frees_exactly_one_and_is_idempotent(client):
    s=snapshot(client); c=next(c for c in active(s) if c['issue']=='clear' and c['block']=='C02')
    for missing in ('clearanceConfirmed','exitConfirmed'):
        e=gate(c['id']);e[missing]=False
        assert command(client,s,e).status_code==422
    key=str(uuid4());r=command(client,s,gate(c['id']),key=key)
    assert r.status_code==200 and len(active(r))==1779
    assert len(r.json()['run']['departures'])==1
    replay=command(client,s,gate(c['id']),key=key)
    assert replay.status_code==200 and replay.json()['revision']==r.json()['revision']
    assert len(active(replay))==1779
    assert command(client,r,gate(c['id'])).status_code==409
    assert client.get('/api/yard/ports/la/containers',params={'container_id':c['id']}).json()['total']==0
    detail=client.get('/api/yard/ports/la/containers/'+c['id']).json()
    assert detail['container']['yardStatus']=='departed'
    assert sum(b['capacity'] for b in r.json()['blocks'])==2592
    block=next(b for b in r.json()['blocks'] if b['id']=='C02')
    assert not any(x['bay']==c['bay'] and x['row']==c['row'] for x in block['containers'])


def test_independent_customs_power_and_prior_scenario_work_remain_blockers(client):
    s=advance(client,snapshot(client),dict(type='scenario',scenario='power'))
    c=next(c for c in active(s) if c['issue']=='customs' and c['plug'] and c['plug']['circuit']=='R1')
    occupied_before=sum(bool(x['plug']) for x in active(s) if x['block']==c['block'])
    s=resolve(client,s,c['id'],'power','power')
    fixed=next(x for x in active(s) if x['id']==c['id'])
    assert [a['issue'] for a in fixed['assessments']['power']]==['customs']
    e=gate(c['id']);e['scenario']='power'
    assert command(client,s,e).status_code==409
    s=resolve(client,s,c['id'],'customs','power')
    s=advance(client,s,e)
    assert len(active(s))==1779
    assert sum(bool(x['plug']) for x in active(s) if x['block']==c['block'])==occupied_before-1
    remaining=next(x for x in active(s) if x['plug'] and x['plug']['circuit']=='R1' and x['issue']=='clear')
    s=advance(client,s,dict(type='review',containerId=remaining['id'],issue='power',scenario='power',choice='accepted',note=''))
    s=advance(client,s,dict(type='scenario',scenario='routine'))
    assert command(client,s,gate(remaining['id'])).status_code==409


def test_stale_updates_key_reuse_and_concurrent_gate_out_cannot_lose_inventory(client):
    initial=snapshot(client); c=next(c for c in active(initial) if c['issue']=='clear')
    key=str(uuid4());e=gate(c['id'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:command(client,initial,e,key=key),range(2)))
    assert [r.status_code for r in results]==[200,200]
    assert len(active(snapshot(client)))==1779
    altered=dict(e,evidence='SIM DIFFERENT')
    assert command(client,initial,altered,key=key).status_code==409
    assert command(client,initial,dict(type='scenario',scenario='power')).status_code==412
    latest=snapshot(client); c2=next(c for c in active(latest) if c['issue']=='clear')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:command(client,latest,gate(c2['id'])),range(2)))
    assert sorted(r.status_code for r in results)==[200,412]
    assert len(active(snapshot(client)))==1778


def test_new_observation_reopens_a_resolved_exception_without_erasing_prior_evidence(client):
    s=snapshot(client);c=next(c for c in active(s) if c['issue']=='sensor')
    s=resolve(client,s,c['id'],'sensor')
    s=advance(client,s,dict(type='observe',containerId=c['id'],issue='sensor',note='SIM fresh telemetry silence'))
    current=next(x for x in active(s) if x['id']==c['id'])
    assert 'sensor' in [a['issue'] for a in current['assessments']['routine']]
    assert current['observationVersion']==1
    assert s.json()['run']['jobs'][0]['stage']=='resolved'
    assert s.json()['run']['jobs'][0]['evidence']=='SIMULATED verified reference'
    assert not s.json()['run']['resolutions']
    s=advance(client,s,dict(type='review',containerId=c['id'],issue='sensor',scenario='routine',choice='accepted',note='SIM recurrence accepted'))
    assert len(s.json()['run']['jobs'])==2
    assert len({j['key'] for j in s.json()['run']['jobs']})==2
    assert client.get('/api/yard/ports/la/audit').json()['events'][1]['type']=='observe'


def test_new_measurement_invalidates_pending_verification_and_preserves_other_holds(client):
    s=snapshot(client);c=next(c for c in active(s) if c['cargo']=='reefer' and c['issue']=='customs')
    s=advance(client,s,dict(type='observe',containerId=c['id'],issue='temperature',note='SIM new temperature'))
    s=advance(client,s,dict(type='review',containerId=c['id'],issue='temperature',scenario='routine',choice='accepted',note=''))
    key=s.json()['run']['jobs'][0]['key']
    s=advance(client,s,dict(type='start',key=key));s=advance(client,s,dict(type='complete_work',key=key,note='SIM old completion'))
    old=s
    s=advance(client,s,dict(type='observe',containerId=c['id'],issue='temperature',note='SIM newer temperature'))
    assert s.json()['run']['jobs'][0]['stage']=='in_progress'
    assert command(client,old,dict(type='verify',key=key,confirmed=True,evidence='SIM stale')).status_code==412
    assert command(client,s,dict(type='verify',key=key,confirmed=True,evidence='SIM stale')).status_code==409
    current=next(x for x in active(s) if x['id']==c['id'])
    assert {'customs','temperature'}=={a['issue'] for a in current['assessments']['routine']}


def test_database_failure_rolls_back_resolution_stage_and_revision(client,monkeypatch):
    s=snapshot(client);c=next(c for c in active(s) if c['issue']=='customs')
    s=advance(client,s,dict(type='review',containerId=c['id'],issue='customs',scenario='routine',choice='accepted',note=''))
    key=s.json()['run']['jobs'][0]['key']
    s=advance(client,s,dict(type='start',key=key));s=advance(client,s,dict(type='complete_work',key=key,note='SIM completion'))
    def fail(*args): raise sqlite3.OperationalError('secret DB internals')
    monkeypatch.setattr(client.app.state.yard_store,'_save_job',fail)
    r=command(client,s,dict(type='verify',key=key,confirmed=True,evidence='SIM authority verified'))
    assert r.status_code==503 and 'secret DB' not in r.text
    latest=snapshot(client)
    assert latest.json()['revision']==s.json()['revision']
    assert latest.json()['run']['jobs'][0]['stage']=='awaiting_verification'
    assert latest.json()['run']['resolutions']==[]


def test_restart_keeps_records_cookie_capability_and_idempotency(settings):
    with TestClient(create_app(settings)) as c:
        c.post('/api/yard/session',headers=HEADERS);s=snapshot(c)
        row=next(c for c in active(s) if c['issue']=='clear')
        key=str(uuid4());event=gate(row['id']);r=command(c,s,event,key=key)
        cookie=c.cookies.get('gate_yard_workspace');etag=s.headers['etag']
        assert r.status_code==200
    with TestClient(create_app(settings)) as c:
        c.cookies.set('gate_yard_workspace',cookie,path='/api/yard')
        assert c.post('/api/yard/session',headers=HEADERS).status_code==200
        s=snapshot(c);assert len(active(s))==1779
        assert command(c,etag,event,key=key).status_code==200
        assert len(active(snapshot(c)))==1779
    with sqlite3.connect(settings.yard_database_path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM yard_departures').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM yard_audit WHERE type="gate_out"').fetchone()[0]==1


def test_workspace_and_port_boundaries_and_reset_archive(settings):
    app=create_app(settings)
    with TestClient(app) as c, TestClient(app) as other:
        c.post('/api/yard/session',headers=HEADERS);other.post('/api/yard/session',headers=HEADERS)
        s=snapshot(c);r=advance(c,s,gate(next(x for x in active(s) if x['issue']=='clear')['id']))
        assert len(active(snapshot(other)))==1780
        assert len(active(snapshot(c,'rotterdam')))==1142
        old_id=r.json()['runId'];r=advance(c,r,dict(type='reset'))
        assert r.json()['runId']!=old_id and r.json()['run']['seed']==27150
        assert command(c,s,dict(type='scenario',scenario='power')).status_code==412
        assert any(e['type']=='gate_out' for e in c.get('/api/yard/ports/la/audit').json()['events'])
        with sqlite3.connect(settings.yard_database_path) as db:
            assert db.execute('SELECT active FROM yard_runs WHERE id=?',(old_id,)).fetchone()[0]==0
            assert db.execute('SELECT count(*) FROM yard_departures WHERE run=?',(old_id,)).fetchone()[0]==1


def test_no_agent_calls_and_strict_untrusted_mutations(client,settings,monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('The yard must not call the agent')
    monkeypatch.setattr('gate_triage.agent.run_agent',forbidden)
    s=snapshot(client)
    assert client.post('/api/yard/ports/la/commands',json={'type':'reset'},headers=HEADERS).status_code==428
    assert client.post('/api/yard/ports/la/commands',json={'type':'reset'},headers={**HEADERS,'If-Match':s.headers['etag']}).status_code==400
    assert command(client,s,dict(type='reset',state={'departures':[]})).status_code==422
    c=next(x for x in active(s) if x['cargo']=='dry')
    assert command(client,s,dict(type='observe',containerId=c['id'],issue='temperature',note='SIM bad type')).status_code==422
    e=gate(c['id']);e['exitConfirmed']='true'
    assert command(client,s,e).status_code==422
    e=gate(c['id']);e['at']='2000-01-01'
    assert command(client,s,e).status_code==422
    assert advance(client,s,dict(type='scenario',scenario='combined')).json()['agentEnabled'] is False
    r=client.post('/api/yard/session',headers=HEADERS)
    assert 'httponly' in r.headers['set-cookie'].lower() and 'samesite=strict' in r.headers['set-cookie'].lower()
    with TestClient(create_app(settings)) as anonymous:
        assert snapshot(anonymous).status_code==401


def test_ambiguous_failure_after_commit_can_be_retried_without_duplicate_departure(client,monkeypatch):
    state=snapshot(client);c=next(c for c in active(state) if c['issue']=='clear')
    real=client.app.state.yard_store.command
    first=True
    def lost_response(*args):
        nonlocal first
        result=real(*args)
        if first:
            first=False
            raise sqlite3.OperationalError('SIMULATED lost response after commit')
        return result
    monkeypatch.setattr(client.app.state.yard_store,'command',lost_response)
    key=str(uuid4());event=gate(c['id'])
    assert command(client,state,event,key=key).status_code==503
    retried=command(client,state,event,key=key)
    assert retried.status_code==200 and len(active(retried))==1779
    assert len(retried.json()['run']['departures'])==1
    events=client.get('/api/yard/ports/la/audit').json()['events']
    assert len([e for e in events if e['type']=='gate_out'])==1
