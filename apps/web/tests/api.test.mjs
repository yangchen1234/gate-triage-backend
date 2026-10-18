import test from 'node:test';
import assert from 'node:assert/strict';

let serial = 0;
const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } });
async function isolatedApi(initial = '') {
  const storage = new Map(initial ? [['gate-triage-console-token', initial]] : []);
  globalThis.sessionStorage = { getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, v) };
  return { ...(await import(`../src/api.ts?test=${++serial}`)), storage };
}

test('StrictMode-style bootstrap calls share one session POST and never generate a plan', async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url, init }); return response({ token: 'session-test-token', revision: 1 }); };
  const mod = await isolatedApi();
  const first = mod.loadSession(), second = mod.loadSession();
  assert.equal(first, second);
  await Promise.all([first, second]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/console/session');
  assert.equal(calls[0].init.method, 'POST');
  assert.deepEqual([...mod.storage.keys()], ['gate-triage-console-token']);
});
test('config unwraps metadata and never stores API key in browser storage', async () => {
  const mod = await isolatedApi('session-test-token'); const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url, init }); return response({ model: { configured: init.method === 'PUT', model: init.method === 'PUT' ? 'account-model-id' : null } }); };
  const configured = await mod.api.configure('test-only-placeholder', 'account-model-id');
  assert.equal(configured.configured, true);
  assert.equal(configured.model, 'account-model-id');
  assert.equal(calls[0].init.headers.get('X-Console-Token'), 'session-test-token');
  assert.equal([...mod.storage.values()].includes('test-only-placeholder'), false);
  assert.equal((await mod.api.disconnect()).configured, false);
});
test('team access sends only the code in a scoped request and never stores it', async () => {
  const mod = await isolatedApi('session-test-token'); const calls = [];
  const status = { configured: true, server_available: true, source: 'render_environment', model: 'team-model-id', key_expires_at: '2026-10-17T10:15:00Z' };
  globalThis.fetch = async (url, init) => { calls.push({ url, init }); return response({ model: status }); };
  assert.deepEqual(await mod.api.connectTeam('test-only-team-code'), status);
  assert.equal(calls[0].url, '/api/console/agent/team');
  assert.equal(calls[0].init.method, 'PUT');
  assert.equal(calls[0].init.headers.get('X-Console-Token'), 'session-test-token');
  assert.equal(calls[0].init.credentials, 'same-origin');
  assert.deepEqual(JSON.parse(calls[0].init.body), { access_code: 'test-only-team-code' });
  assert.deepEqual([...mod.storage.entries()], [['gate-triage-console-token', 'session-test-token']]);
  await mod.api.disconnect();
  assert.equal(calls[1].url, '/api/console/agent/config');
  assert.equal(calls[1].init.method, 'DELETE');
});
test('rejected team code does not masquerade as an expired browser session', async () => {
  const mod = await isolatedApi('session-test-token');
  globalThis.fetch = async () => response({ detail: 'Team access code is invalid' }, 403);
  await assert.rejects(mod.api.connectTeam('incorrect-test-code'), err => err instanceof mod.ApiError && err.status === 403 && err.message === 'Team access code is invalid');
  assert.equal(mod.storage.get('gate-triage-console-token'), 'session-test-token');
});
test('plan POST transmits stable idempotency key, revision and explicit use_model', async () => {
  const mod = await isolatedApi('session-test-token'); let captured;
  globalThis.fetch = async (_url, init) => { captured = init; return response({ id: 'job-test', status: 'queued' }, 202); };
  await mod.api.generate({ top_n: 3, use_model: false }, 4, 'same-request-key');
  assert.equal(captured.headers.get('If-Match'), '4');
  assert.equal(captured.headers.get('Idempotency-Key'), 'same-request-key');
  assert.deepEqual(JSON.parse(captured.body), { top_n: 3, use_model: false });
});
test('old session response cannot expire a newly created session', async () => {
  const mod = await isolatedApi('old-session-token'); let finishOld;
  globalThis.fetch = async (_url, init) => init.method === 'POST' ? response({ token: 'fresh-session-token', revision: 1 }) : new Promise(resolve => { finishOld = resolve; });
  const previous = mod.api.session();
  const discarded = assert.rejects(previous, err => err instanceof mod.ApiError && err.status === -1);
  await mod.newSession(); finishOld(response({ detail: 'Session expired' }, 401)); await discarded;
  assert.equal(mod.storage.get('gate-triage-console-token'), 'fresh-session-token');
});
test('conflict errors retain safe server details instead of misreporting every conflict as stale', async () => {
  const mod = await isolatedApi('session-test-token');
  globalThis.fetch = async () => response({ detail: 'A plan is already running; wait before configuring Claude' }, 409);
  await assert.rejects(mod.api.configure('test-only-placeholder', 'account-model-id'), /already running/);
});
test('reconnecting replaces an expired bootstrap so remounting does not create another session', async () => {
  const mod = await isolatedApi('expired-token'); let creates = 0;
  globalThis.fetch = async (_url, init) => init.method === 'POST'
    ? (creates++, response({ token: 'reconnected-token', revision: 1 }))
    : response({ detail: 'Session expired' }, 401);
  await assert.rejects(mod.loadSession(), err => err.status === 401);
  await mod.newSession();
  await mod.loadSession();
  await mod.loadSession();
  assert.equal(creates, 1);
});
