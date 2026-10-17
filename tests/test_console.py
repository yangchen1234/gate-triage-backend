"""Console capability isolation, replay safety and paid-provider boundaries."""
from copy import deepcopy
import json
from pathlib import Path
from threading import Event
from time import sleep
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from gate_triage import agent, console
from gate_triage.config import Settings
from gate_triage.score import score_all


@pytest.fixture
def api():
    app = FastAPI()
    store = console.install_console(app, Settings())
    with TestClient(app) as client:
        yield client, store
    store.close()


def create(client):
    result = client.post('/api/console/session')
    assert result.status_code == 201
    data = result.json()
    return data, {'X-Console-Token': data['token'], 'If-Match': str(data['revision'])}


def launch(client, headers, **body):
    return client.post('/api/console/plans', json={'top_n': 5, 'use_model': False, **body},
                       headers={**headers, 'Idempotency-Key': str(uuid4())})


def wait(client, headers, job_id):
    for _ in range(100):
        response = client.get(f'/api/console/plans/{job_id}', headers=headers)
        assert response.status_code == 200
        result = response.json()
        if result['status'] not in ('queued', 'running'):
            return result
        sleep(.02)
    pytest.fail('plan did not finish')


def test_synthetic_ports_and_session_isolation(api):
    client, store = api
    ports = client.get('/api/console/ports').json()
    assert [(p['code'], p['currency']) for p in ports['ports']] == [('LAX', 'USD'), ('SHA', 'CNY'), ('RTM', 'EUR')]
    assert 'Synthetic' in ports['tariff_notice']
    first, a = create(client)
    second, b = create(client)
    assert first['revision'] == 1 and len(first['queue']) == 100
    assert first['data_kind'] == 'synthetic'
    assert first['model']['configured'] is False
    changed = client.post('/api/console/scenario', json={'lanes_open': 4, 'port': 'SHA'}, headers=a).json()
    assert changed['revision'] == 2
    assert changed['stats']['currency'] == 'CNY'
    assert all(c['currency'] == 'CNY' for c in changed['queue'])
    assert client.get('/api/console/session', headers=b).json()['scenario']['port'] == 'LAX'
    assert 'token' not in client.get('/api/console/session', headers=a).json()
    assert client.get('/api/console/session').status_code == 401
    assert client.get('/api/console/session', headers={'X-Console-Token': 'wrong'}).status_code == 401
    assert store.raw == json.loads(Path('data/containers.json').read_text())


def test_atomic_revision_and_plan_approval_membership(api):
    client, _ = api
    snapshot, headers = create(client)
    assert client.post('/api/console/scenario', json={'lanes_open': 4}, headers={'X-Console-Token': snapshot['token']}).status_code == 428
    response = launch(client, headers)
    assert response.status_code == 202
    job = wait(client, headers, response.json()['id'])
    assert job['status'] == 'succeeded' and not job['stale']
    assert job['result']['agent_mode'] == 'deterministic'
    assert job['result']['nothing_is_sent_automatically'] is True
    assert job['result']['model_requests'] == 0
    action = job['result']['actions'][0]
    decision = {k: action[k] for k in ('container_id', 'blocker')}
    decision.update(decision='approved', note='check with authorized operator')
    path = f"/api/console/plans/{job['id']}/decisions"
    accepted = client.post(path, json=decision, headers=headers)
    assert accepted.status_code == 200
    assert accepted.json()['result']['actions'][0]['approval']['dispatch'] == 'manual_follow_up_only'
    assert client.post(path, json={**decision, 'container_id': 'FAKE'}, headers=headers).status_code == 404
    _, other = create(client)
    assert client.get(f"/api/console/plans/{job['id']}", headers=other).status_code == 404
    assert client.post('/api/console/scenario', json={'lanes_open': 4}, headers=headers).status_code == 200
    assert client.post('/api/console/scenario', json={'lanes_open': 8}, headers=headers).status_code == 409
    newer = {**headers, 'If-Match': '2'}
    assert client.post(path, json=decision, headers=newer).status_code == 409
    assert client.get(f"/api/console/plans/{job['id']}", headers=newer).json()['stale'] is True
    assert client.get('/api/console/session', headers=newer).json()['revision'] == 2


def test_paid_dispatch_idempotent_and_fixed_anthropic_config(api, monkeypatch):
    client, _ = api
    _, headers = create(client)
    key = 'sk-ant-do-not-leak-private-test'
    response = client.put('/api/console/agent/config', json={'api_key': key, 'model': 'claude-sonnet-4-6'}, headers=headers)
    assert response.status_code == 200 and key not in response.text
    assert response.json()['model']['configured'] is True
    assert client.get('/api/console/session', headers=headers).json()['revision'] == 1
    entered, release, calls = Event(), Event(), []
    def fake(raw, scenario, top_n, cfg):
        calls.append({**cfg})
        entered.set()
        assert release.wait(3)
        return {'actions': [], 'summary': 'test', 'nothing_is_sent_automatically': True}
    monkeypatch.setattr(console, 'run_agent', fake)
    idem = str(uuid4())
    req_headers = {**headers, 'Idempotency-Key': idem}
    try:
        response = client.post('/api/console/plans', json={'use_model': True}, headers=req_headers)
        assert response.status_code == 202 and entered.wait(2)
        retry = client.post('/api/console/plans', json={'use_model': True}, headers=req_headers)
        assert retry.json()['id'] == response.json()['id']
        assert launch(client, headers, use_model=True).status_code == 409
        assert client.post('/api/console/plans', json={'use_model': False}, headers=req_headers).status_code == 409
        assert len(calls) == 1 and calls[0]['base_url'] == 'https://api.anthropic.com/v1/'
        assert calls[0]['api_key'] == key
        assert key not in retry.text
        assert client.delete('/api/console/agent/config', headers=headers).json()['model']['configured'] is False
        assert calls[0]['_cancel'].is_set()
    finally:
        release.set()
    finished = wait(client, headers, response.json()['id'])
    assert key not in json.dumps(finished)
    assert client.get('/api/console/session', headers=headers).json()['model']['configured'] is False


@pytest.mark.parametrize('payload', [
    {'api_key': 'sk-ant-secret-private-key', 'model': 'https://attacker.example'},
    {'api_key': 'sk-ant-secret-private-key', 'model': 'claude-sonnet-4-6', 'base_url': 'https://evil'},
    {'api_key': {'secret': 'sk-ant-secret-private-key'}, 'model': 'claude-sonnet-4-6'},
    {'api_key': 'sk-ant-secret-private-key with whitespace', 'model': 'claude-sonnet-4-6'},
    {'api_key': 'sk-ant-secret-private-key' * 200, 'model': 'claude-sonnet-4-6'},
])
def test_config_validation_never_echoes_key(api, payload):
    client, _ = api
    _, headers = create(client)
    response = client.put('/api/console/agent/config', json=payload, headers=headers)
    assert response.status_code == 422
    assert 'sk-ant-secret' not in response.text
    malformed = client.put('/api/console/agent/config', content='{"api_key":"sk-ant-secret-private-key",', headers={**headers, 'Content-Type': 'application/json'})
    assert malformed.status_code == 422 and 'sk-ant-secret' not in malformed.text
    oversized = client.put('/api/console/agent/config', json={'api_key': 'secret' * 5000}, headers=headers)
    assert oversized.status_code == 413 and 'secret' not in oversized.text


def test_expiry_clears_keys_and_capacity_does_not_evict(api, monkeypatch):
    client, store = api
    data, headers = create(client)
    client.put('/api/console/agent/config', json={'api_key': 'sk-ant-private-secret-key', 'model': 'claude-sonnet-4-6'}, headers=headers)
    session = store.sessions[data['token']]
    session.key_expires = 0
    assert client.get('/api/console/session', headers=headers).json()['model']['configured'] is False
    assert session.key is None and session.cancel.is_set()
    monkeypatch.setattr(console, 'MAX_SESSIONS', 1)
    assert client.post('/api/console/session').status_code == 503
    assert client.get('/api/console/session', headers=headers).status_code == 200
    session.expires = 0
    assert client.get('/api/console/session', headers=headers).status_code == 401
    assert data['token'] not in store.sessions


def test_worker_exception_does_not_leak_provider_key(api, monkeypatch, caplog):
    client, _ = api
    _, headers = create(client)
    def failing(*args, **kwargs):
        raise RuntimeError('Authorization sk-ant-extremely-private-key')
    monkeypatch.setattr(console, 'run_agent', failing)
    response = launch(client, headers)
    result = wait(client, headers, response.json()['id'])
    assert result['status'] == 'failed'
    assert 'private-key' not in json.dumps(result) + caplog.text


def test_agent_explicit_none_never_uses_environment(monkeypatch):
    rows = json.loads(Path('data/containers.json').read_text())
    monkeypatch.setenv('LLM_BASE_URL', 'https://api.anthropic.com/v1/')
    monkeypatch.setenv('LLM_MODEL', 'claude-sonnet-4-6')
    monkeypatch.setenv('LLM_API_KEY', 'sk-ant-private-key')
    monkeypatch.setattr(agent, '_client', lambda _: pytest.fail('unexpected paid invocation'))
    plan = agent.run_agent(rows, {'lanes_open': 8, 'port': 'LAX'}, cfg=None)
    assert plan['agent_mode'] == 'deterministic' and plan['model_requests'] == 0


def test_model_failure_is_sanitized_and_still_has_deterministic_plan(monkeypatch):
    rows = json.loads(Path('data/containers.json').read_text())
    def fail(_):
        raise RuntimeError('sk-ant-super-private-key')
    monkeypatch.setattr(agent, '_client', fail)
    result = agent.run_agent(rows, {'lanes_open': 8, 'port': 'LAX'}, cfg={'base_url': 'https://api.anthropic.com/v1/', 'model': 'claude-sonnet-4-6', 'api_key': 'sk-ant-super-private-key'})
    assert result['actions'] and result['agent_mode'] == 'deterministic (model unavailable)'
    assert all(a['draft']['source'] == 'template' for a in result['actions'])
    assert 'private-key' not in json.dumps(result)


def test_model_malformed_final_is_not_reported_as_cloud_success(monkeypatch):
    rows = json.loads(Path('data/containers.json').read_text())
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='not JSON', tool_calls=None))]))))
    monkeypatch.setattr(agent, '_client', lambda _: fake)
    result = agent.run_agent(rows, {'lanes_open': 8, 'port': 'LAX'}, cfg={'base_url': 'https://api.anthropic.com/v1/', 'model': 'claude-sonnet-4-6', 'api_key': 'sk-ant-private-key'})
    assert result['agent_mode'] == 'deterministic (model unavailable)'
    assert result['model_requests'] <= 6


def test_offline_customs_never_releases_and_independent_warnings_remain():
    rows = json.loads(Path('data/containers.json').read_text())
    scored = score_all(rows, {'lanes_open': 8, 'customs_online': False, 'power_zone_b': False, 'port': 'LAX'})
    assert all(c['action'] != 'release' for c in scored)
    for c in scored:
        assert 'customs offline' in c['reason']
        if c['sources']['customs']['hold']:
            assert 'do not release' in c['reason']
        if c['zone'] == 'B' and c['sources']['reefer']:
            assert 'zone B unpowered' in c['reason']


def test_claude_compat_omits_unsupported_sampling_and_enforces_limits(monkeypatch):
    calls, constructor = [], []
    class FakeClient:
        def __init__(self, **kwargs):
            constructor.append(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"subject":"Check declaration","body":"Please verify the evidence."}', tool_calls=None))])
    monkeypatch.setattr(agent, 'OpenAI', FakeClient)
    cfg = {'base_url': 'https://api.anthropic.com/v1/', 'api_key': 'sk-ant-private-test', 'model': 'claude-sonnet-4-6'}
    raw = json.loads(Path('data/containers.json').read_text())
    action = agent.next_actions(raw, {'lanes_open': 8, 'port': 'LAX'})['actions'][0]
    draft = agent.draft_outreach(action, cfg)
    assert draft['source'] == 'cloud'
    assert constructor[0]['max_retries'] == 0 and constructor[0]['timeout'] == 20
    assert calls[0]['max_tokens'] == 800 and 0 < calls[0]['timeout'] <= 20
    assert 'temperature' not in calls[0] and 'response_format' not in calls[0]
    for _ in range(20):
        agent.draft_outreach(action, cfg)
    assert len(calls) == 6  # shared budget includes the first call


@pytest.mark.parametrize('reply', [
    '{"summary":"ok","actions":[123]}',
    '{"summary":"ok","actions":[]}',
    '{"summary":"ok","actions":[{"container_id":"FAKE","blocker":"customs_hold","why":"invented"}]}',
    '{"summary":null,"actions":[]}',
])
def test_unverifiable_model_plan_falls_back_without_more_paid_drafting(monkeypatch, reply):
    rows = json.loads(Path('data/containers.json').read_text())
    calls = []
    def complete(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply, tool_calls=None))])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))
    monkeypatch.setattr(agent, '_client', lambda _: fake)
    result = agent.run_agent(rows, {'lanes_open': 8, 'port': 'LAX'}, cfg={'base_url': 'https://api.anthropic.com/v1/', 'model': 'claude-sonnet-4-6', 'api_key': 'sk-ant-private-key'})
    assert result['agent_mode'] == 'deterministic (model unavailable)'
    assert result['actions'] and all(a['draft']['source'] == 'template' for a in result['actions'])
    assert len(calls) == 1


def test_agent_tools_enforce_argument_bounds():
    rows = json.loads(Path('data/containers.json').read_text())
    _, tools = agent.make_tools(rows, {'lanes_open': 8, 'port': 'LAX'})
    assert 'error' in tools['get_plan'](top_n=1000000)
    assert 'error' in tools['get_plan'](top_n=True)
    assert 'error' in tools['simulate_fix']('x' * 2000, 'customs_hold')
    assert 'error' in tools['simulate_fix'](rows[0]['container_id'], 'arbitrary')


def test_global_model_concurrency_releases_slots_after_failures(api, monkeypatch):
    client, _ = api
    sessions = [create(client)[1] for _ in range(3)]
    for headers in sessions:
        assert client.put('/api/console/agent/config', json={'api_key': 'sk-ant-private-secret-key', 'model': 'claude-sonnet-4-6'}, headers=headers).status_code == 200
    entered, release = [], Event()
    def failing(*args, **kwargs):
        entered.append(True)
        assert release.wait(3)
        raise RuntimeError('sk-ant-secret')
    monkeypatch.setattr(console, 'run_agent', failing)
    try:
        first = launch(client, sessions[0], use_model=True)
        second = launch(client, sessions[1], use_model=True)
        for _ in range(100):
            if len(entered) == 2:
                break
            sleep(.01)
        third = launch(client, sessions[2], use_model=True)
        assert third.status_code == 429
    finally:
        release.set()
    assert wait(client, sessions[0], first.json()['id'])['status'] == 'failed'
    assert wait(client, sessions[1], second.json()['id'])['status'] == 'failed'
    later = launch(client, sessions[2], use_model=True)
    assert later.status_code == 202
    assert wait(client, sessions[2], later.json()['id'])['status'] == 'failed'


def test_zero_lanes_and_customs_outage_do_not_claim_unlocked_release(api):
    client, _ = api
    _, headers = create(client)
    snap = client.post('/api/console/scenario', json={'customs_online': False, 'lanes_open': 0}, headers=headers).json()
    headers['If-Match'] = str(snap['revision'])
    response = launch(client, headers)
    result = wait(client, headers, response.json()['id'])['result']
    assert result['gate_capacity_today'] == 0 and result['total_unlocked_per_day'] == 0
    assert result['actions'] == []


def test_request_creation_rate_limit(api):
    client, _ = api
    for _ in range(6):
        assert client.post('/api/console/session').status_code == 201
    result = client.post('/api/console/session')
    assert result.status_code == 429 and result.headers['Retry-After'] == '60'


def test_decision_retry_is_idempotent_and_conflicting_concurrent_write_loses(api):
    from concurrent.futures import ThreadPoolExecutor
    client, _ = api
    _, headers = create(client)
    response = launch(client, headers)
    job = wait(client, headers, response.json()['id'])
    action = job['result']['actions'][0]
    body = {k: action[k] for k in ('container_id', 'blocker')}
    path = f"/api/console/plans/{job['id']}/decisions"
    def decide(status):
        return client.post(path, json={**body, 'decision': status, 'note': 'human review'}, headers=headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(decide, ['approved', 'rejected']))
    assert sorted([a.status_code, b.status_code]) == [200, 409]
    accepted = a if a.status_code == 200 else b
    status = accepted.json()['result']['actions'][0]['approval']['status']
    retry = decide(status)
    assert retry.status_code == 200 and retry.json() == accepted.json()
    changed_note = client.post(path, json={**body, 'decision': status, 'note': 'silently overwritten'}, headers=headers)
    assert changed_note.status_code == 409


@pytest.mark.parametrize('port', ['LAX', 'SHA', 'RTM'])
def test_console_stats_match_legacy_original_order_fifo_with_arrival_ties(api, port):
    from gate_triage.service import QueueService
    client, _ = api
    _, headers = create(client)
    snapshot = client.post('/api/console/scenario', json={'port': port, 'lanes_open': 6}, headers=headers).json()
    reference = QueueService(Settings()).update({'port': port, 'lanes_open': 6}).stats
    for field, expected in reference.items():
        assert snapshot['stats'][field] == expected
    assert snapshot['stats']['currency'] == {'LAX': 'USD', 'SHA': 'CNY', 'RTM': 'EUR'}[port]


def test_empty_model_draft_is_a_template_fallback(monkeypatch):
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"subject":"  ","body":""}', tool_calls=None))]))))
    monkeypatch.setattr(agent, '_client', lambda _: fake)
    rows = json.loads(Path('data/containers.json').read_text())
    action = agent.next_actions(rows, {'lanes_open': 8, 'port': 'LAX'})['actions'][0]
    cfg = {'base_url': 'https://api.anthropic.com/v1/', 'model': 'claude-sonnet-4-6', 'api_key': 'sk-ant-private-key'}
    result = agent.draft_outreach(action, cfg)
    assert result['source'] == 'template' and result['subject'].strip() and result['body'].strip()
