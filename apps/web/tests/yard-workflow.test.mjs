import test from 'node:test';
import assert from 'node:assert/strict';
import { makeDemo, summarize, issuesFor, plugSummary, queryYardInventory, supplyFor } from '../src/yard-demo.ts';
import { createYardRun, transitionWorkflow, projectYard, projectContainer, parseYardRun, workKey, releaseBlockers } from '../src/yard-workflow.ts';
const blocks = makeDemo(), all = blocks.flatMap(b => b.containers);
const at = '2026-10-17T20:00:00.000Z';
function step(run, event) { const result = transitionWorkflow(run, { at, ...event }, blocks); assert.equal(result.ok, true, result.error); return result.run; }
function resolve(run, c, issue, scenario = 'routine') {
  run = step(run, { type: 'review', containerId: c.id, issue, scenario, choice: 'accepted', note: 'Simulated handoff' });
  const key = workKey(c.id, issue);
  run = step(run, { type: 'start', key });
  run = step(run, { type: 'complete_work', key, note: 'SIMULATED work completed' });
  return step(run, { type: 'verify', key, confirmed: true, evidence: 'SIMULATED verified result' });
}
const exit = (c, scenario = 'routine') => ({ type: 'gate_out', containerId: c.id, scenario, evidence: 'SIMULATED exit ticket', clearanceConfirmed: true, exitConfirmed: true });

test('acceptance queues work while inventory, flags and capacity remain unchanged', () => {
  const original = createYardRun(), c = all.find(c => c.issue === 'customs');
  const run = step(original, { type: 'review', containerId: c.id, issue: 'customs', scenario: 'routine', choice: 'accepted', note: 'Contact authority' });
  assert.equal(run.jobs[0].stage, 'queued');
  assert.equal(original.jobs.length, 0);
  assert.deepEqual(summarize(projectYard(blocks, run), 'routine'), summarize(blocks, 'routine'));
  assert.ok(issuesFor(projectContainer(c, run), 'routine').includes('customs'));
  assert.equal(transitionWorkflow(run, { type: 'review', containerId: c.id, issue: 'customs', scenario: 'combined', choice: 'accepted', note: '', at }, blocks).ok, false);
});
test('task transitions require ordered work, completion notes and verification evidence', () => {
  const c = all.find(c => c.issue === 'weight');
  let run = step(createYardRun(), { type: 'review', containerId: c.id, issue: 'weight', scenario: 'routine', choice: 'accepted', note: '' });
  const key = run.jobs[0].key;
  for (const e of [{ type: 'verify', key, evidence: 'SIM verified', confirmed: true }, { type: 'complete_work', key, note: 'SIM done' }]) assert.equal(transitionWorkflow(run, { ...e, at }, blocks).ok, false);
  run = step(run, { type: 'start', key });
  assert.equal(transitionWorkflow(run, { type: 'complete_work', key, note: '', at }, blocks).ok, false);
  run = step(run, { type: 'complete_work', key, note: 'SIM reweigh and record corrected' });
  assert.equal(projectContainer(c, run).issue, 'weight');
  assert.equal(transitionWorkflow(run, { type: 'verify', key, evidence: 'SIM result', confirmed: false, at }, blocks).ok, false);
  assert.equal(transitionWorkflow(run, { type: 'verify', key, evidence: ' ', confirmed: true, at }, blocks).ok, false);
  assert.equal(transitionWorkflow(run, { type: 'verify', key, evidence: 'SIM result', confirmed: true, at: '2020-01-01' }, blocks).ok, false);
  run = step(run, { type: 'verify', key, evidence: 'SIM corrected record verified', confirmed: true });
  assert.equal(run.jobs[0].stage, 'resolved');
  assert.equal(projectContainer(c, run).issue, 'clear');
  assert.equal(projectContainer(c, run).declared, c.weight);
  assert.deepEqual(summarize(projectYard(blocks, run), 'routine').containers, all.length);
  assert.equal(transitionWorkflow(run, { type: 'verify', key, evidence: 'SIM repeated', confirmed: true, at }, blocks).ok, false);
});
test('resolving power for one unit preserves customs hold, circuit outage and other affected units', () => {
  const c = all.find(c => c.plug?.circuit === 'R1' && c.issue === 'customs');
  let run = resolve(createYardRun(), c, 'power', 'power');
  const projected = projectContainer(c, run);
  assert.equal(supplyFor(projected, 'power'), 'verified-unit-backup');
  assert.deepEqual(issuesFor(projected, 'power'), ['customs']);
  assert.equal(transitionWorkflow(run, { ...exit(c, 'power'), at }, blocks).ok, false);
  const before = plugSummary(blocks.find(b => b.id === c.block), 'power');
  const after = plugSummary(projectYard(blocks, run).find(b => b.id === c.block), 'power');
  assert.equal(after.connected, before.connected);
  assert.equal(after.affected, before.affected - 1);
  assert.equal(after.available, 0);
  run = resolve(run, c, 'customs', 'power');
  assert.deepEqual(issuesFor(projectContainer(c, run), 'power'), []);
  assert.equal(releaseBlockers(projectContainer(c, run), run, 'power').length, 0);
});
test('normalization keeps a container in stock; only confirmed physical gate-out removes it once', () => {
  const c = all.find(c => c.issue === 'sensor');
  let run = resolve(createYardRun(), c, 'sensor');
  assert.equal(projectYard(blocks, run).flatMap(b => b.containers).length, all.length);
  for (const flags of [{ exitConfirmed: false }, { clearanceConfirmed: false }, { evidence: '' }]) assert.equal(transitionWorkflow(run, { ...exit(c), ...flags, at }, blocks).ok, false);
  run = step(run, exit(c));
  const yard = projectYard(blocks, run), stats = summarize(yard, 'routine');
  assert.equal(stats.containers, all.length - 1);
  assert.equal(stats.capacity, summarize(blocks, 'routine').capacity);
  assert.equal(queryYardInventory(yard.flatMap(b => b.containers), { containerId: c.id, company: '' }).length, 0);
  assert.equal(projectContainer(c, run).yardStatus, 'departed');
  assert.equal(run.jobs[0].stage, 'resolved');
  assert.equal(transitionWorkflow(run, { ...exit(c), at }, blocks).ok, false);
  for (const scenario of ['routine', 'power', 'combined']) assert.equal(summarize(yard, scenario).containers, all.length - 1);
});
test('a normal single-tier gate-out empties its ground cell without moving other tier positions', () => {
  const b = blocks.find(b => b.id === 'C02'), c = b.containers.find(c => c.issue === 'clear');
  const run = step(createYardRun(), exit(c));
  const next = projectYard(blocks, run).find(x => x.id === b.id);
  assert.equal(next.containers.filter(x => x.bay === c.bay && x.row === c.row).length, 0);
  assert.deepEqual(next.containers, b.containers.filter(x => x.id !== c.id).map(x => projectContainer(x, run)));
  assert.equal(run.departures[0].tier, c.tier);
});
test('reefer departure frees occupancy but never energizes an offline circuit', () => {
  const c = all.find(c => c.plug?.circuit === 'R1' && c.issue === 'clear');
  let run = resolve(createYardRun(), c, 'power', 'power');
  run = step(run, exit(c, 'power'));
  const before = plugSummary(blocks.find(b => b.id === c.block), 'power');
  const after = plugSummary(projectYard(blocks, run).find(b => b.id === c.block), 'power');
  assert.equal(after.connected, before.connected - 1);
  assert.equal(after.capacity, before.capacity);
  assert.equal(after.available, 0);
});
test('one verified alternate access does not reopen the shared exit for other units', () => {
  const c = all.find(c => c.perishable && c.issue === 'clear');
  const run = resolve(createYardRun(), c, 'congestion', 'congestion');
  assert.deepEqual(issuesFor(projectContainer(c, run), 'congestion'), []);
  const other = all.find(x => x.perishable && x.id !== c.id);
  assert.ok(issuesFor(projectContainer(other, run), 'congestion').includes('congestion'));
});
test('pending accepted work blocks gate-out even when its scenario is switched off', () => {
  const c = all.find(c => c.plug?.circuit === 'R1' && c.issue === 'clear');
  const run = step(createYardRun(), { type: 'review', containerId: c.id, issue: 'power', scenario: 'power', choice: 'accepted', note: '' });
  assert.deepEqual(issuesFor(projectContainer(c, run), 'routine'), []);
  assert.equal(transitionWorkflow(run, { ...exit(c), at }, blocks).ok, false);
});
test('saved run restores verified state and rejects malformed or contradictory occupancy changes', () => {
  const c = all.find(c => c.issue === 'customs');
  const resolved = resolve(createYardRun(), c, 'customs');
  const run = step(resolved, exit(c));
  assert.deepEqual(parseYardRun(JSON.stringify(run)), run);
  for (const value of [null, '', '{}', '{invalid', JSON.stringify({ ...run, seed: -1 }), JSON.stringify({ ...run, departures: [...run.departures, run.departures[0]] }), JSON.stringify({ ...run, resolutions: [] }), JSON.stringify({ ...run, jobs: [...run.jobs, run.jobs[0]] }), JSON.stringify({ ...run, departures: [{ ...run.departures[0], tier: 100 }] })]) assert.equal(parseYardRun(value), null);
  const malicious = { ...createYardRun(), departures: run.departures };
  assert.equal(parseYardRun(JSON.stringify(malicious)), null, 'held container cannot disappear from a corrupted cache');
});
