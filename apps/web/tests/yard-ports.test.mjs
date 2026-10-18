import test from 'node:test';
import assert from 'node:assert/strict';
import { makeDemo, PORTS, summarize, issuesFor, plugSummary, isPerishable } from '../src/yard-demo.ts';
import { createYardRun, loadYardRun, saveYardRun, parseYardRun, transitionWorkflow, projectYard } from '../src/yard-workflow.ts';
import { translateYard, formatYardNumber, formatYardTime } from '../src/yard-language.ts';
const at = '2026-10-17T22:00:00Z';
test('Rotterdam has a reproducible eight-block, two-row cohort, distinct from the unchanged LA default', () => {
  const la = makeDemo(), rt = makeDemo(undefined, 'rotterdam');
  assert.equal(la.length, 12); assert.equal(rt.length, 8);
  assert.equal(summarize(la, 'routine').containers, 1780);
  assert.deepEqual(rt, makeDemo(PORTS.rotterdam.seed, 'rotterdam'));
  assert.notDeepEqual(rt, makeDemo(PORTS.rotterdam.seed + 1, 'rotterdam'));
  assert.equal(new Set(rt.map(b => b.row)).size, 2);
  assert.deepEqual(rt.map(b => b.id), ['A01', 'A03', 'B01', 'B02', 'B03', 'C01', 'C03', 'C04']);
  const ids = new Set(la.flatMap(b => b.containers.map(c => c.id)));
  assert.ok(rt.flatMap(b => b.containers).every(c => c.id.startsWith('RTDM') && !ids.has(c.id)));
  for (const b of rt) {
    assert.ok(b.containers.length <= b.capacity);
    assert.equal(new Set(b.containers.map(c => `${c.bay}:${c.row}:${c.tier}`)).size, b.containers.length);
    assert.ok(b.containers.every(c => c.tier <= b.maxTiers && (!c.plug || c.row <= b.pluggedRows)));
    const p = plugSummary(b, 'routine'); assert.equal(p.connected + p.available, p.capacity);
  }
});
test('all Rotterdam disruption effects stay within the modeled circuit and access boundaries', () => {
  const rt = makeDemo(undefined, 'rotterdam');
  const held = rt.find(b => b.id === 'B01').containers.find(c => c.issue === 'customs' && c.plug);
  assert.ok(held); assert.deepEqual(new Set(issuesFor(held, 'power')), new Set(['power', 'customs']));
  for (const c of rt.flatMap(b => b.containers)) {
    assert.equal(issuesFor(c, 'power').includes('power'), c.plug?.circuit === 'R1');
    assert.equal(issuesFor(c, 'congestion').includes('congestion'), isPerishable(c));
  }
});
test('Rotterdam gate-out and cache validation use its own fixture rather than the LA IDs', () => {
  let run = createYardRun(undefined, 'rotterdam');
  const rt = makeDemo(run.seed, run.port), c = rt[0].containers.find(c => c.issue === 'clear');
  const result = transitionWorkflow(run, { type: 'gate_out', containerId: c.id, scenario: 'routine', evidence: 'SIM uitrit R-1', clearanceConfirmed: true, exitConfirmed: true, at });
  assert.equal(result.ok, true); run = result.run;
  assert.equal(summarize(projectYard(rt, run), 'routine').containers, summarize(rt, 'routine').containers - 1);
  assert.deepEqual(parseYardRun(JSON.stringify(run)), run);
  assert.equal(parseYardRun(JSON.stringify({ ...run, port: 'la' })), null);
  const legacy = createYardRun(); delete legacy.port;
  assert.equal(parseYardRun(JSON.stringify(legacy)).port, 'la');
});
test('switching port storage preserves each cohort, accepted work and departures independently', () => {
  const oldWindow = globalThis.window, storage = new Map();
  globalThis.window = { localStorage: { getItem: k => storage.get(k) || null, setItem: (k,v) => storage.set(k,v) } };
  try {
    const la = createYardRun(), rt = createYardRun(undefined, 'rotterdam');
    const c = makeDemo(rt.seed, rt.port).flatMap(b => b.containers).find(c => c.issue === 'customs');
    const result = transitionWorkflow(rt, { type: 'review', containerId: c.id, issue: 'customs', scenario: 'routine', choice: 'accepted', note: 'NL test', at });
    assert.equal(result.ok, true); assert.equal(saveYardRun(la), true); assert.equal(saveYardRun(result.run), true);
    assert.deepEqual(loadYardRun('la'), la); assert.deepEqual(loadYardRun('rotterdam'), result.run);
    assert.equal(storage.size, 2);
    const laKey = [...storage.keys()].find(k => !k.includes('rotterdam'));
    storage.set(laKey, JSON.stringify(result.run));
    assert.deepEqual(loadYardRun('la'), createYardRun(), 'wrong-port cache cannot cross the boundary');
  } finally { globalThis.window = oldWindow; }
});
test('Dutch copy translates static labels and full dynamic messages while preserving identifiers', () => {
  assert.equal(translateYard('Containers in yard', 'rotterdam'), 'Containers op terrein');
  assert.equal(translateYard('12 synthetic blocks', 'la'), '12 synthetic blocks');
  assert.equal(translateYard('8 synthetic blocks', 'rotterdam'), '8 gesimuleerde blokken');
  assert.equal(translateYard('Select stack B01 bay 2, row 1, 3 containers', 'rotterdam'), 'Selecteer stapel B01 vak 2, rij 1, 3 containers');
  assert.equal(translateYard('Routine: Monitor → Now: Do first', 'rotterdam'), 'Regulier: Bewaken → Nu: Direct aanpakken');
  assert.equal(translateYard(' RTDM4000001 ', 'rotterdam'), ' RTDM4000001 ');
  assert.equal(translateYard('MAEU', 'rotterdam'), 'MAEU');
  assert.equal(translateYard(128, 'rotterdam'), 128);
  assert.equal(formatYardNumber(1780, 'rotterdam'), '1.780');
  assert.equal(formatYardNumber(1780, 'la'), '1,780');
  assert.match(formatYardTime('2026-10-17T22:00:00Z', 'rotterdam'), /18-10-2026.*00:00/);
});

test('stack selection options retain top-to-ground order and include exact empty tier positions', async () => {
  const { stackTierSlots } = await import('../src/yard-demo.ts');
  for (const port of ['la', 'rotterdam']) {
    const b = makeDemo(undefined, port).find(b => b.id === 'B01');
    const c = b.containers[0], original = structuredClone(b);
    const tiers = stackTierSlots(b, c.bay, c.row);
    assert.deepEqual(tiers.map(t => t.tier), [3, 2, 1]);
    assert.equal(tiers.filter(t => t.container).length, b.containers.filter(x => x.bay === c.bay && x.row === c.row).length);
    for (const tier of tiers) if (tier.container) assert.equal(tier.container.tier, tier.tier);
    const vacant = stackTierSlots({ ...b, containers: b.containers.filter(x => !(x.bay === c.bay && x.row === c.row)) }, c.bay, c.row);
    assert.ok(vacant.every(t => t.container === null)); assert.equal(vacant.length, b.maxTiers);
    assert.deepEqual(b, original);
  }
});
