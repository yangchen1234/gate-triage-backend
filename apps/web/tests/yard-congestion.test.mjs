import test from 'node:test';
import assert from 'node:assert/strict';
import { makeDemo, actionsFor, actionFor, issuesFor, congestionExposure, isPerishable, compareActions, priorityChange, exceptionColor, stackExceptionState, PERISHABLE_COLOR, PHYSICAL_ALERT_COLOR } from '../src/yard-demo.ts';

test('congestion promotes dependent perishables from routine stock and exposes the margin', () => {
  for (const port of ['la','rotterdam']) {
    const all=makeDemo(undefined,port).flatMap(b=>b.containers), original=structuredClone(all);
    const fresh=all.find(c=>isPerishable(c)&&c.issue==='clear');
    assert.deepEqual(actionsFor(fresh,'routine'),[]);
    const action=actionsFor(fresh,'congestion')[0], exposure=congestionExposure(fresh,'congestion');
    assert.equal(action.issue,'congestion');assert.equal(action.quadrant,'do');
    assert.equal(exposure.delayDays,1);assert.equal(exposure.remainingDays,fresh.pickupWindowDays-1);
    assert.equal(priorityChange(fresh,'congestion').promoted,true);
    assert.notEqual(exceptionColor(fresh,'routine'),PERISHABLE_COLOR);
    assert.equal(exceptionColor(fresh,'congestion'),PERISHABLE_COLOR);
    const pharma=all.find(c=>c.cargo==='reefer'&&!isPerishable(c));
    assert.ok(pharma);assert.ok(!issuesFor(pharma,'congestion').includes('congestion'));
    assert.ok(!issuesFor({...fresh,yardStatus:'departed'},'congestion').length);
    assert.ok(!issuesFor({...fresh,verifiedAlternateAccess:true},'congestion').includes('congestion'));
    assert.deepEqual(all,original);
  }
});
test('each stack highlights delayed perishables on any tier while physical alerts stay red', () => {
  for (const port of ['la', 'rotterdam']) {
    const all = makeDemo(undefined, port).flatMap(b => b.containers);
    const fresh = all.find(c => c.cargo === 'reefer' && isPerishable(c) && c.issue === 'clear');
    const routine = { ...fresh, id: fresh.id + '-other', cargo: 'dry', perishable: false, plug: null, issue: 'clear' };
    const stack = [routine, fresh];
    assert.equal(stackExceptionState(stack, 'routine').delayedPerishables, 0);
    assert.notEqual(stackExceptionState(stack, 'routine').color, PERISHABLE_COLOR);
    const delayed = stackExceptionState(stack, 'congestion');
    assert.equal(delayed.color, PERISHABLE_COLOR); assert.equal(delayed.delayedPerishables, 1);
    const alarm = { ...fresh, id: fresh.id + '-alarm', issue: 'temperature' };
    const mixed = stackExceptionState([...stack, alarm], 'congestion');
    assert.equal(mixed.color, PHYSICAL_ALERT_COLOR); assert.equal(mixed.physicalAlerts, 1);
    assert.equal(exceptionColor(alarm, 'congestion'), PHYSICAL_ALERT_COLOR);
    assert.equal(stackExceptionState([fresh], 'combined').color, fresh.plug.circuit === 'R1' ? PHYSICAL_ALERT_COLOR : PERISHABLE_COLOR);
    assert.equal(stackExceptionState([{ ...fresh, verifiedAlternateAccess: true }], 'congestion').delayedPerishables, 0);
    assert.equal(stackExceptionState([{ ...fresh, yardStatus: 'departed' }], 'congestion').delayedPerishables, 0);
    assert.equal(stackExceptionState([], 'congestion').color, '#f0f3f4');
    const empty = all.find(c => c.block === 'C04' && c.issue === 'clear');
    assert.equal(stackExceptionState([empty], 'congestion').color, exceptionColor(empty, 'routine'));
    let changed = 0;
    for (const block of makeDemo(undefined, port)) {
      const stacks = new Map();
      for (const c of block.containers) { const key = `${c.bay}:${c.row}`; stacks.set(key, [...(stacks.get(key) || []), c]); }
      for (const units of stacks.values()) if (stackExceptionState(units, 'congestion').color === PERISHABLE_COLOR && stackExceptionState(units, 'routine').color !== PERISHABLE_COLOR) changed++;
    }
    assert.ok(changed > 40, `${port}: many individual stack units visibly turn yellow`);
  }
});
test('perishable prerequisites rise and the queue respects urgency, importance and tighter windows', () => {
  const fresh=makeDemo().flatMap(b=>b.containers).find(c=>isPerishable(c));
  const held={...fresh,issue:'customs',pickupWindowDays:3};
  const normal=actionFor(held,'customs','routine'), congested=actionFor(held,'customs','congestion');
  assert.equal(normal.quadrant,'plan');assert.equal(congested.quadrant,'do');
  assert.ok(congested.importance>normal.importance&&congested.urgency>normal.urgency);
  assert.ok(issuesFor(held,'congestion').includes('customs'));
  const soon=actionFor({...fresh,pickupWindowDays:1},'congestion','congestion');
  const later=actionFor({...fresh,pickupWindowDays:2},'congestion','congestion');
  assert.ok(compareActions(soon,later)<0);
  const empty=makeDemo().find(b=>b.id==='C04').containers[0];
  assert.equal(actionFor(empty,'congestion','congestion').quadrant,'coordinate');
  assert.ok(compareActions(soon,actionFor(empty,'congestion','congestion'))<0);
});

test('whole-day delay is shared across the yard and ambient perishables stay unpowered', () => {
  for (const port of ['la','rotterdam']) {
    const all=makeDemo(undefined,port).flatMap(b=>b.containers);
    const ambient=all.filter(c=>c.cargo==='dry'&&c.perishable);
    assert.ok(ambient.length>10);
    assert.ok(new Set(ambient.map(c=>c.block)).size>=6);
    assert.ok(ambient.every(c=>c.plug===null&&c.commodity==='Ambient produce'));
    for(const c of all){
      const e=congestionExposure(c,'congestion');
      assert.equal(e.route,'YARD-EXIT');assert.equal(e.delayDays,1);
      assert.ok(Number.isInteger(e.windowDays)&&e.windowDays>=1);
      assert.ok(Number.isInteger(e.remainingDays));
      assert.equal(issuesFor(c,'congestion').includes('congestion'),isPerishable(c));
      if(c.cargo==='empty'||c.cargo==='hazmat')assert.equal(isPerishable(c),false);
    }
  }
});
