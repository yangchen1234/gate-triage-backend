import test from 'node:test';
import assert from 'node:assert/strict';
import { actionFor, actionsFor, makeDemo, summarize, issuesFor, primaryIssue, selectContainers, plugSummary, supplyFor, queryYardInventory } from '../src/yard-demo.ts';

test('demo inventories are reproducible, unique, and fit their declared physical slots', () => {
  const blocks = makeDemo(), all = blocks.flatMap(b => b.containers);
  assert.deepEqual(blocks, makeDemo());
  assert.notDeepEqual(blocks, makeDemo(27150));
  assert.equal(new Set(all.map(c => c.id)).size, all.length);
  for (const b of blocks) {
    assert.ok(b.containers.length <= b.capacity);
    assert.equal(new Set(b.containers.map(c => `${c.bay}:${c.row}:${c.tier}`)).size, b.containers.length);
  }
  const stats = summarize(blocks, 'routine');
  assert.equal(stats.containers, all.length);
  assert.equal(stats.capacity, blocks.reduce((n, b) => n + 18 * 4 * b.maxTiers, 0));
  assert.ok(stats.urgent <= stats.exceptions && stats.exceptions <= stats.containers);
});
test('disruptions preserve the cohort and independent customs holds', () => {
  const blocks = makeDemo(), original = structuredClone(blocks);
  const heldReefer = { ...blocks.find(b => b.id === 'B01').containers.find(c => c.plug), issue: 'customs' };
  assert.deepEqual(issuesFor(heldReefer, 'power'), ['power', 'customs']);
  const normal = summarize(blocks, 'routine'), combined = summarize(blocks, 'combined');
  assert.equal(normal.containers, combined.containers);
  assert.equal(normal.capacity, combined.capacity);
  assert.ok(combined.exceptions > normal.exceptions);
  assert.deepEqual(blocks, original);
});
test('power follows an assigned circuit, not zone names; congestion stays scoped', () => {
  const base = { ...makeDemo()[0].containers[0], issue: 'clear', plug: null };
  assert.deepEqual(issuesFor({ ...base, block: 'B01', cargo: 'reefer' }, 'power'), []);
  assert.deepEqual(issuesFor({ ...base, block: 'B03', cargo: 'dry' }, 'power'), []);
  assert.deepEqual(issuesFor({ ...base, block: 'B01', cargo: 'reefer', plug: { id: 'test', circuit: 'R1' } }, 'power'), ['power']);
  assert.deepEqual(issuesFor({ ...base, block: 'C01', cargo: 'reefer', plug: { id: 'test', circuit: 'R2' } }, 'power'), []);
  assert.deepEqual(issuesFor({ ...base, block: 'C03' }, 'congestion'), ['congestion']);
  assert.deepEqual(issuesFor({ ...base, block: 'C02' }, 'congestion'), []);
});
test('infrastructure has unique, finite plug assignments and heterogeneous zone limits', () => {
  for (const seed of [27149, 27150, 1, 999]) {
    const blocks = makeDemo(seed), plugs = blocks.flatMap(b => b.containers.filter(c => c.plug).map(c => c.plug.id));
    assert.equal(new Set(plugs).size, plugs.length);
    assert.equal(blocks.filter(b => b.plugCapacity > 0).length, 3);
    assert.ok(new Set(blocks.map(b => b.maxTiers)).size > 1);
    for (const b of blocks) {
      for (const c of b.containers) {
        assert.ok(c.tier <= b.maxTiers);
        if (c.cargo === 'reefer') { assert.ok(c.plug); assert.ok(c.row <= b.pluggedRows); assert.equal(c.plug.circuit, b.circuit); }
        else assert.equal(c.plug, null);
      }
      const p = plugSummary(b, 'routine'), disrupted = plugSummary(b, 'power');
      assert.ok(p.available >= 0);
      assert.equal(p.capacity, p.connected + p.available);
      assert.equal(disrupted.available, b.circuit === 'R1' ? 0 : p.available);
    }
  }
});
test('action importance and urgency are independent and respond to disruption, not random redraws', () => {
  const c = { ...makeDemo().find(b => b.id === 'B01').containers.find(c => c.plug), issue: 'sensor', reported: 40, criticalCargo: false };
  assert.equal(actionFor(c, 'sensor', 'routine').quadrant, 'monitor');
  assert.equal(actionFor({ ...c, reported: 125 }, 'sensor', 'routine').quadrant, 'coordinate');
  assert.equal(actionFor({ ...c, reported: 40, criticalCargo: true }, 'sensor', 'routine').quadrant, 'plan');
  assert.equal(actionFor({ ...c, reported: 125, criticalCargo: true }, 'sensor', 'routine').quadrant, 'do');
  assert.equal(actionFor({ ...c, reported: 89 }, 'sensor', 'routine').quadrant, 'monitor');
  assert.equal(actionFor({ ...c, reported: 90 }, 'sensor', 'routine').quadrant, 'coordinate');
  assert.equal(actionFor({ ...c, handlingWindowMinutes: 60 }, 'weight', 'routine').quadrant, 'do');
  assert.equal(actionFor({ ...c, handlingWindowMinutes: 61 }, 'weight', 'routine').quadrant, 'plan');
  const outage = actionsFor(c, 'power');
  assert.equal(outage.length, 2);
  assert.ok(outage.every(a => a.quadrant === 'do'));
  assert.equal(supplyFor(c, 'routine'), 'energized');
  assert.equal(supplyFor(c, 'power'), 'interrupted');
  assert.equal(actionFor(c, 'sensor', 'routine').quadrant, 'monitor');
});
test('independent hold follow-up survives emergency care and a changed priority is not release', () => {
  const c = { ...makeDemo().find(b => b.id === 'B01').containers.find(c => c.plug), issue: 'customs', handlingWindowMinutes: 30 };
  assert.equal(actionFor(c, 'customs', 'routine').quadrant, 'do');
  const emergency = actionsFor(c, 'combined');
  assert.deepEqual(new Set(emergency.map(a => a.issue)), new Set(['customs', 'power']));
  assert.equal(emergency.find(a => a.issue === 'customs').quadrant, 'plan');
  assert.equal(emergency.find(a => a.issue === 'power').quadrant, 'do');
  assert.equal(c.issue, 'customs');
  const all = makeDemo().flatMap(b => b.containers);
  for (const scenario of ['routine', 'power', 'congestion', 'combined']) {
    const actions = all.flatMap(c => actionsFor(c, scenario));
    assert.equal(new Set(actions.map(a => a.id)).size, actions.length);
    assert.ok(actions.every(a => a.reasons.length > 0 && a.importance >= 0 && a.importance <= 100 && a.urgency >= 0 && a.urgency <= 100));
  }
});
test('search, block and exception filters compose without changing source data', () => {
  const all = makeDemo().flatMap(b => b.containers), original = structuredClone(all);
  const row = all.find(c => c.issue !== 'clear');
  assert.ok(row);
  assert.equal(selectContainers(all, 'routine', row.id.toLowerCase(), row.block, true)[0].id, row.id);
  assert.equal(selectContainers(all, 'routine', row.id, 'nonexistent', true).length, 0);
  assert.equal(selectContainers(all, 'routine', '', 'all', false).length, all.length);
  assert.equal(selectContainers(all, 'routine', '', 'all', true).length, all.filter(c => primaryIssue(c, 'routine') !== 'clear').length);
  assert.deepEqual(all, original);
});
test('inventory lookup finds every current carrier container, including normal records, and excludes departures', () => {
  const all = makeDemo().flatMap(b => b.containers), original = structuredClone(all);
  const departed = { ...all.find(c => c.carrier === 'MAEU'), id: 'SIMU9999999', yardStatus: 'departed' };
  const data = [...all, departed];
  const byName = queryYardInventory(data, { containerId: '', company: 'Maersk' });
  const byCode = queryYardInventory(data, { containerId: '', company: ' maEu ' });
  assert.deepEqual(byName, byCode);
  assert.equal(byName.length, all.filter(c => c.carrier === 'MAEU').length);
  assert.ok(byName.some(c => c.issue === 'clear'));
  assert.ok(!byName.some(c => c.yardStatus === 'departed'));
  assert.equal(queryYardInventory(data, { containerId: '', company: '' }).length, all.length);
  const hapag = queryYardInventory(all, { containerId: '', company: 'hapag lloyd' });
  assert.equal(hapag.length, all.filter(c => c.carrier === 'HLCU').length);
  assert.deepEqual(all, original);
});
test('inventory lookup composes number and company, handles partial numbers and valid empty states', () => {
  const all = makeDemo().flatMap(b => b.containers), c = all[0];
  assert.deepEqual(queryYardInventory(all, { containerId: ` ${c.id.toLowerCase().replace('simu', 'simu-')} `, company: c.carrier }), [c]);
  assert.equal(queryYardInventory(all, { containerId: c.id, company: 'does-not-exist' }).length, 0);
  assert.equal(queryYardInventory(all, { containerId: '!!!', company: '' }).length, 0);
  assert.equal(queryYardInventory(all, { containerId: 'SIMU9999999', company: '' }).length, 0);
  const subset = queryYardInventory(all, { containerId: c.id.slice(0, -2), company: c.carrier });
  assert.ok(subset.includes(c));
  assert.ok(subset.every(x => x.id.startsWith(c.id.slice(0, -2)) && x.carrier === c.carrier));
});
