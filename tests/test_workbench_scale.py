"""Relational scale API: generation, durable jobs, paging and phase controls."""
from __future__ import annotations
import copy
import time
import uuid
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from gate_triage.workbench.api import router as api_router, install_handlers
from gate_triage.workbench.db import Job, Workspace, configure_database, get_database
from gate_triage.workbench.emergency import router as emergency_router, source_retrieval
from gate_triage.workbench.scale import ScaleEvent, ScaleMovement, ScaleRun, router, seed_scale, scale_restrictions
from gate_triage.workbench.spatial import incident_catalog, router as spatial_router
from gate_triage.workbench.worker import start_worker, stop_worker

@pytest.fixture
def client(tmp_path):
    stop_worker(); configure_database(f"sqlite:///{tmp_path/'scale.db'}")
    app=FastAPI();install_handlers(app);app.include_router(api_router);app.include_router(router);app.include_router(emergency_router);app.include_router(spatial_router)
    with TestClient(app) as client:yield client
    stop_worker()

def make(client):
    r=client.post('/api/v1/workspaces',json={'name':'Scale API check','mode':'SIMULATION','scenario_id':'normal_operations','seed':17},headers={'Idempotency-Key':str(uuid.uuid4())})
    assert r.status_code==201,r.text
    return r.json()['data']

def path(w):return f"/api/v1/workspaces/{w['id']}"
def auth(w,rev=None,key=None):return {'X-Workspace-Token':w['token'],'If-Match':str(rev or w['revision']),'Idempotency-Key':key or str(uuid.uuid4())}
def fresh(client,w):return {**client.get(path(w),headers=auth(w)).json()['data'],'token':w['token']}
def generate(client,w,profile='la_average_day',worker=False):
    r=client.post(path(w)+'/scale',json={'profile':profile,'seed':17},headers=auth(w))
    assert r.status_code==202,r.text
    job=r.json()['data']
    if worker:
        start_worker();deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            result=client.get(path(w)+'/jobs/'+job['id'],headers=auth(w)).json()['data']
            if result['status'] in {'succeeded','failed'}:break
            time.sleep(.05)
        assert result['status']=='succeeded',result
    else:seed_scale({'id':job['id'],'workspace_id':w['id'],'payload':{'run_id':job['run_id']}})
    return job

def test_scale_sql_generation_worker_paging_and_independent_clock(client):
    w=make(client);job=generate(client,w,worker=True)
    response=client.get(path(w)+'/scale',headers=auth(w));data=response.json()['data']
    assert data['run']['total_records']==17002
    assert data['summary']['teu_total']==28053
    assert len(data['summary']['terminals'])==7
    assert data['clock_independent_from_precision'] is True
    page=client.get(path(w)+'/scale/containers?limit=50&terminal_id=terminal-fenix',headers=auth(w)).json()['data']
    assert len(page['items'])==50 and all(row['terminal_id']=='terminal-fenix' for row in page['items'])
    assert page['total']>50
    assert client.get(path(w)+'/scale/containers?limit=101',headers=auth(w)).status_code==422
    w=fresh(client,w);key=str(uuid.uuid4())
    advanced=client.post(path(w)+'/scale/advance',json={'minutes':120},headers=auth(w,key=key))
    assert advanced.status_code==200,advanced.text
    assert advanced.json()['data']['summary']['completed_movements']>0
    replay=client.post(path(w)+'/scale/advance',json={'minutes':120},headers=auth(w,key=key))
    assert replay.json()==advanced.json()
    assert fresh(client,w)['snapshot']['clock_min']==0
    with get_database().session() as s:
        assert s.get(Workspace,w['id']).state['scale_clock_min']==120
        assert len(list(s.scalars(select(ScaleEvent))))==2
        assert s.scalar(select(func.count()).select_from(ScaleMovement))==17002
        assert s.execute(text('SELECT version_num FROM wb_alembic_version')).scalar_one()=='wb_0003'
    configure_database(get_database().url)
    assert client.get(path(w)+'/scale',headers=auth(w)).json()['data']['run']['clock_min']==120
    other=make(client)
    assert client.get(path(w)+'/scale',headers=auth(other)).status_code==404
    assert client.get(path(other)+'/scale',headers=auth(other)).json()['data']['run'] is None

def test_generation_retry_reuses_cohort_without_duplicate_rows(client):
    w=make(client);job=generate(client,w)
    again=seed_scale({'id':job['id'],'workspace_id':w['id'],'payload':{'run_id':job['run_id']}})
    assert again['reused'] is True
    with get_database().session() as s:
        assert s.scalar(select(func.count()).select_from(ScaleMovement))==17002
        assert s.scalar(select(func.count()).select_from(ScaleEvent))==1

def test_failed_generation_is_atomic(client,monkeypatch):
    from gate_triage.workbench import scale_simulation
    w=make(client)
    r=client.post(path(w)+'/scale',json={},headers=auth(w));job=r.json()['data']
    original=scale_simulation.iter_movement_batches
    def broken(*args,**kwargs):
        yield next(original(*args,**kwargs))
        raise ValueError('Injected generator failure')
    monkeypatch.setattr(scale_simulation,'iter_movement_batches',broken)
    with pytest.raises(ValueError,match='Injected'):seed_scale({'id':job['id'],'workspace_id':w['id'],'payload':{'run_id':job['run_id']}})
    with get_database().session() as s:
        assert s.scalar(select(func.count()).select_from(ScaleMovement))==0
        assert s.get(ScaleRun,job['run_id']).status=='failed'

def test_horizon_rejects_without_creating_fake_progress(client):
    w=make(client);job=generate(client,w)
    with get_database().session() as s:
        run=s.get(ScaleRun,job['run_id']);run.clock_min=run.horizon_minutes
    w=fresh(client,w)
    r=client.post(path(w)+'/scale/advance',json={'minutes':15},headers=auth(w))
    assert r.status_code==409 and r.json()['error']['code']=='SCALE_HORIZON_REACHED'
    assert fresh(client,w)['revision']==w['revision']
    with get_database().session() as s:assert s.scalar(select(func.count()).select_from(ScaleEvent))==1

def test_bulk_incident_scope_and_independent_deadline(client):
    w=make(client);generate(client,w);w=fresh(client,w)
    bad=client.post(path(w)+'/incidents',json={'scenario_id':'battery_access_2024','scope_id':'zone-reefer','severity':'critical'},headers=auth(w))
    assert bad.status_code==201,bad.text
    assert not bad.json()['data']['incident']['scale_assessment']['applicable']
    w=fresh(client,w)
    incident=client.post(path(w)+'/incidents',json={'scenario_id':'storm_wind','scope_id':'terminal-apm','severity':'critical'},headers=auth(w))
    assert incident.status_code==201,incident.text
    record=incident.json()['data']['incident'];assert record['scale_assessment']['applicable']
    with get_database().session() as s:
        rules=scale_restrictions(s.get(Workspace,w['id']).state)
    assert not rules['terminal-apm']['closed']
    assert rules['terminal-apm']['phase_incidents']==[{'scenario_id':'storm_wind','started_at_min':0}]
    assert 'phase_incidents' not in rules['terminal-fenix']
    r=client.post(path(w)+'/scale/advance',json={'minutes':15},headers=auth(fresh(client,w)))
    assert r.status_code==200,r.text
    listed=client.get(path(w)+'/incidents',headers=auth(w)).json()['data']['items']
    view=next(item for item in listed if item['id']==record['id'])
    assert view['escalation']['overdue'] is True
    assert view['escalation']['precision_elapsed_minutes']==0
    assert view['escalation']['scale_elapsed_minutes']==15

def test_retrieval_filters_unrelated_disaster_year_hits():
    scenario=next(row for row in incident_catalog() if row['id']=='battery_access_2024')
    result=source_retrieval(scenario)
    assert result['source_guard']['policy']=='scenario_historical_urls_or_relevant_product_policy'
    refs={row['url'] for row in scenario['source_refs']}
    assert result['passages']
    assert all(row['url'] in refs or row['kind']=='product_policy' for row in result['passages'])
    assert all('usace' not in row['url'].lower() for row in result['sources'])


def test_scale_incident_cannot_leak_into_replacement_run(client):
    w=make(client);first=generate(client,w)
    r=client.post(path(w)+'/scale/advance',json={'minutes':60},headers=auth(fresh(client,w)))
    assert r.status_code==200,r.text
    incident=client.post(path(w)+'/incidents',json={'scenario_id':'storm_wind','scope_id':'terminal-apm','severity':'critical'},headers=auth(fresh(client,w))).json()['data']['incident']
    assert incident['scale_created_at_min']==60
    denied=client.post(path(w)+'/scale',json={},headers=auth(fresh(client,w)))
    assert denied.status_code==409 and denied.json()['error']['code']=='SCALE_INCIDENT_ACTIVE'
    with get_database().session() as s:
        original=copy.deepcopy(s.get(Workspace,w['id']).state)
    assert not scale_restrictions(original,run_id='a-new-independent-run')['terminal-apm'].get('phase_incidents')
    recovered=client.post(path(w)+f"/incidents/{incident['id']}/resolve",json={'acknowledged':True,'note':'Confirmed synthetic recovery'},headers=auth(fresh(client,w)))
    assert recovered.status_code==200,recovered.text
    # Direct helper seeding leaves a queued Job; mark that test harness job as
    # completed so the API's independent outstanding-job guard is satisfied.
    with get_database().session() as s:s.get(Job,first['id']).status='succeeded'
    second=generate(client,fresh(client,w))
    assert second['run_id']!=first['run_id']
    response=client.post(path(w)+'/scale/advance',json={'minutes':15},headers=auth(fresh(client,w)))
    assert response.status_code==200,response.text
    assert response.json()['data']['run']['clock_min']==15


@pytest.mark.parametrize('route,payload',[('/scale',{'seed':True}),('/scale/advance',{'minutes':True}),('/scale/advance',{'minutes':1.5})])
def test_scale_rejects_coerced_numeric_inputs(client,route,payload):
    w=make(client)
    assert client.post(path(w)+route,json=payload,headers=auth(w)).status_code==422
    assert fresh(client,w)['revision']==1


def test_real_postgres_seven_day_relational_cohort_and_guarded_advance():
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    url=os.getenv('WORKBENCH_TEST_POSTGRES_URL')
    if not url:pytest.skip('Set WORKBENCH_TEST_POSTGRES_URL for isolated real-PostgreSQL scale check')
    stop_worker();schema='wb_scale_audit_'+uuid.uuid4().hex
    admin=create_engine(url)
    with admin.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped=make_url(url).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    configure_database(scoped)
    app=FastAPI();install_handlers(app);app.include_router(api_router);app.include_router(router);app.include_router(emergency_router)
    try:
        with TestClient(app) as client:
            w=make(client);generate(client,w,profile='la_seven_day',worker=True)
            data=client.get(path(w)+'/scale',headers=auth(w)).json()['data']
            assert data['run']['total_records']==119014
            assert data['summary']['teu_total']==196371
            assert sum(row['total_records'] for row in data['summary']['terminals'])==119014
            page=client.get(path(w)+'/scale/containers?offset=100000&limit=50',headers=auth(w)).json()['data']
            assert len(page['items'])==50 and page['total']==119014
            from gate_triage.workbench.db import begin_read_snapshot
            from gate_triage.workbench.api import authorized_workspace
            from gate_triage.workbench.scale import latest_run, summary
            # A real committed writer interleaves between the reader's initial
            # workspace/run read and its aggregate read. MVCC preserves one
            # response context without blocking that writer.
            with get_database().session() as reader:
                begin_read_snapshot(reader)
                assert reader.execute(text('SHOW transaction_isolation')).scalar_one()=='repeatable read'
                observed=authorized_workspace(reader,w['id'],w['token'])
                observed_run=latest_run(reader,w['id'])
                assert observed_run.clock_min==0
                assert summary(reader,observed_run)['completed_movements']==0
                response=client.post(path(w)+'/scale/advance',json={'minutes':120},headers=auth(fresh(client,w)))
                assert response.status_code==200,response.text
                assert response.json()['data']['summary']['completed_movements']>0
                assert summary(reader,observed_run)['completed_movements']==0
                reader.refresh(observed)
                assert observed.state['scale_clock_min']==0
            with get_database().session() as reader:
                assert summary(reader,latest_run(reader,w['id']))['completed_movements']>0
            with get_database().session() as s:
                assert s.scalar(select(func.count()).select_from(ScaleMovement).where(ScaleMovement.completed_min>120))==0
                assert s.scalar(select(func.count()).select_from(ScaleMovement))==119014
                assert len(s.get(Workspace,w['id']).state['containers'])==100
    finally:
        stop_worker();configure_database('sqlite:///:memory:')
        with admin.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_precision_reset_cannot_silently_remove_active_scale_incident(client):
    w=make(client);generate(client,w)
    advanced=client.post(path(w)+'/scale/advance',json={'minutes':60},headers=auth(fresh(client,w)))
    assert advanced.status_code==200,advanced.text
    record=client.post(path(w)+'/incidents',json={'scenario_id':'storm_wind','scope_id':'terminal-apm','severity':'critical'},headers=auth(fresh(client,w))).json()['data']['incident']
    denied=client.post(path(w)+'/commands',json={'command':'reset'},headers=auth(fresh(client,w)))
    assert denied.status_code==409 and denied.json()['error']['code']=='INCIDENT_RECOVERY_REQUIRED'
    resolved=client.post(path(w)+f"/incidents/{record['id']}/resolve",json={'acknowledged':True,'note':'Acknowledged safe synthetic recovery'},headers=auth(fresh(client,w)))
    assert resolved.status_code==200,resolved.text
    reset=client.post(path(w)+'/commands',json={'command':'reset'},headers=auth(fresh(client,w)))
    assert reset.status_code==200,reset.text
    with get_database().session() as s:
        assert s.get(Workspace,w['id']).state['scale_clock_min']==60
        assert s.get(Workspace,w['id']).state['scale_run_id']
    assert client.get(path(w)+'/scale',headers=auth(w)).json()['data']['run']['clock_min']==60


def test_map_sql_bulk_counts_clock_isolation_and_overdue_severity(client):
    w=make(client);generate(client,w)
    created=client.post(path(w)+'/incidents',json={'scenario_id':'storm_wind','scope_id':'terminal-apm','severity':'restricted'},headers=auth(fresh(client,w)))
    assert created.status_code==201,created.text
    incident=created.json()['data']['incident']
    assert 'synthetic scale run' in incident['proposal']['summary']
    assert 'scale run' in next(step for step in incident['workflow'] if step['stage']=='validate')['summary']
    advanced=client.post(path(w)+'/scale/advance',json={'minutes':15},headers=auth(fresh(client,w)))
    assert advanced.status_code==200,advanced.text
    mapped=client.get(path(w)+'/map',headers=auth(w));assert mapped.status_code==200,mapped.text
    data=mapped.json()['data']
    assert data['as_of_min']==0
    assert data['scale']['run']['clock_min']==15
    assert len(data['terminals'])==7
    assert sum(row['properties']['scale_metrics']['total_records'] for row in data['terminals'])==17002
    assert sum(row['properties']['scale_metrics']['completed_movements'] for row in data['terminals'])==advanced.json()['data']['summary']['completed_movements']
    apm=next(row['properties'] for row in data['terminals'] if row['properties']['id']=='terminal-apm')
    assert apm['metrics']=={} and apm['container_ids']==[]
    assert apm['scale_severity']=='critical'  # derived overdue escalation, not the original report severity
    report=next(row for row in data['incidents'] if row['id']==incident['id'])
    assert report['escalation']['effective_severity']=='critical'
    assert sum(len(row['properties']['container_ids']) for row in data['terminals'])==100
    assert client.get(path(w)+'/map').status_code==404
    other=make(client)
    assert client.get(path(w)+'/map',headers=auth(other)).status_code==404


def test_map_verified_evidence_changes_readiness_without_completed_work(client):
    w=make(client)
    number=w['snapshot']['hero_id']
    before=client.get(path(w)+'/map',headers=auth(w)).json()['data']
    original=next(row['properties']['metrics'] for row in before['zones'] if row['properties']['id']=='zone-yard')
    command={'command':'evidence','container_id':number,'kind':'weight','values':{'unit':'kg','basis':'container_gross','declared_status':'empty','tare_kg':2200,'measured_kg':2200,'identity_verified':True,'measurement_verified':True}}
    response=client.post(path(w)+'/commands',json=command,headers=auth(w))
    assert response.status_code==200,response.text
    after=client.get(path(w)+'/map',headers=auth(w)).json()['data']
    yard=next(row['properties']['metrics'] for row in after['zones'] if row['properties']['id']=='zone-yard')
    assert yard['satisfied_tasks']==original['satisfied_tasks']+1
    assert yard['completed_operations']==original['completed_operations']==0
    assert after['as_of_min']==0
    assert sum(row['properties']['metrics']['completed_operations'] for row in after['zones'] if row['properties']['operation_type']=='gate_handoff')==0


def test_map_reads_upgraded_vessel_snapshot_without_mutating_legacy_state(client):
    w=make(client)
    with get_database().session() as s:
        row=s.get(Workspace,w['id']);legacy=copy.deepcopy(row.state)
        legacy['engine_revision']=3
        legacy.pop('spatial_operations',None);legacy.pop('spatial_incidents',None)
        for rid in ('quay-crane-1','quay-crane-2','marine-channel-1'):legacy['resources'].pop(rid,None)
        row.state=legacy
    response=client.get(path(w)+'/map',headers=auth(w));assert response.status_code==200,response.text
    data=response.json()['data']
    vessel_zones=[row['properties'] for row in data['zones'] if row['properties']['operation_type'].startswith('vessel_')]
    assert len(vessel_zones)==2
    assert all(row['metrics']['total_operations']>0 for row in vessel_zones)
    assert all(row['metrics']['completed_operations']==0 for row in vessel_zones)
    assert all(row['container_ids']==[] for row in vessel_zones)
    with get_database().session() as s:
        stored=s.get(Workspace,w['id']);assert stored.revision==1 and stored.state==legacy
