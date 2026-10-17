import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_FILTERS, filterQueue, jobIsRunning, jobIsStale, mayDecide, mergeJob, money, preferredPlanId, requestIntent } from '../src/state.ts';

const rows = [
  { container_id: 'A001', carrier_code: 'MAEU', consignee_type: 'hospital', action: 'inspect', cargo_type: 'reefer_pharma', conflict_score: .7, priority: .9, demurrage_per_day: 500, arrived_at: '2026-10-16T00:00:00' },
  { container_id: 'B002', carrier_code: 'MSCU', consignee_type: 'retail', action: 'release', cargo_type: 'general', conflict_score: .1, priority: .7, demurrage_per_day: 700, arrived_at: '2026-10-14T00:00:00' },
  { container_id: 'C003', carrier_code: 'MAEU', consignee_type: 'grocery', action: 'slow', cargo_type: 'reefer_food', conflict_score: .5, priority: .2, demurrage_per_day: 200, arrived_at: '2026-10-15T00:00:00' },
];
const job = { id: 'test-job', status: 'succeeded', input_revision: 2, stale: false, result: null, error: null, created_at: '2026-10-17T00:00:00Z' };

test('queue search, cargo, action and conflict filters compose without mutating data', () => {
  const original = structuredClone(rows);
  assert.deepEqual(filterQueue(rows, { ...DEFAULT_FILTERS, search: ' maeu ', conflict: true }).map(r => r.container_id), ['A001', 'C003']);
  assert.deepEqual(filterQueue(rows, { ...DEFAULT_FILTERS, cargo: 'reefer_pharma', action: 'inspect' }).map(r => r.container_id), ['A001']);
  assert.deepEqual(filterQueue(rows, { ...DEFAULT_FILTERS, search: 'HOSPITAL' }).map(r => r.container_id), ['A001']);
  assert.deepEqual(rows, original);
});
test('sorts local fee, arrival and priority independently', () => {
  assert.deepEqual(filterQueue(rows, { ...DEFAULT_FILTERS, sort: 'fee' }).map(r => r.container_id), ['B002', 'A001', 'C003']);
  assert.deepEqual(filterQueue(rows, { ...DEFAULT_FILTERS, sort: 'arrival' }).map(r => r.container_id), ['B002', 'C003', 'A001']);
  assert.deepEqual(filterQueue(rows, DEFAULT_FILTERS).map(r => r.container_id), ['A001', 'B002', 'C003']);
});
test('only current completed plans can be approved; stale server flag wins', () => {
  assert.equal(mayDecide(job, 2), true);
  assert.equal(mayDecide(job, 3), false);
  assert.equal(jobIsStale({ ...job, stale: true }, 2), true);
  assert.equal(mayDecide({ ...job, status: 'running' }, 2), false);
  assert.equal(mayDecide(null, 2), false);
});
test('delayed running response cannot overwrite a completed job', () => {
  const jobs = [job];
  assert.equal(mergeJob(jobs, { ...job, status: 'running' }), jobs);
  assert.equal(jobIsRunning({ ...job, status: 'queued' }), true);
  assert.equal(jobIsRunning(job), false);
  assert.equal(mergeJob(jobs, { ...job, stale: true })[0].stale, true);
});
test('refresh finds a running job after an ambiguous submission, keeping polling alive', () => {
  const active = { ...job, id: 'active-job', status: 'running' };
  assert.equal(preferredPlanId([job, active], null), active.id);
  assert.equal(preferredPlanId([job, active], job.id), active.id);
  assert.equal(preferredPlanId([job], 'missing-job'), job.id);
  assert.equal(preferredPlanId([], null), null);
});
test('ambiguous plan retries reuse the same intent; changed inputs create a new key', () => {
  let count = 0; const createKey = () => `key-${++count}`;
  const first = requestIntent(null, 1, 5, false, createKey);
  assert.equal(requestIntent(first, 1, 5, false, createKey), first);
  assert.equal(count, 1);
  assert.equal(requestIntent(first, 2, 5, false, createKey).key, 'key-2');
  assert.equal(requestIntent(first, 1, 5, true, createKey).key, 'key-3');
});
test('local currency formatting never labels all ports as USD', () => {
  assert.match(money(500, 'CNY'), /CN¥|CNY/);
  assert.match(money(500, 'EUR'), /€/);
  assert.match(money(500, 'USD'), /\$/);
});
