import test from 'node:test';
import assert from 'node:assert/strict';
import { makeDemo, actionsFor, actionFor, issuesFor, congestionExposure, isPerishable, compareActions, priorityChange, exceptionColor, PERISHABLE_COLOR } from '../src/yard-demo.ts';

test('congestion promotes dependent perishables from routine stock and exposes the margin', () => {
  for (const port of ['la','rotterdam']) {
    const all=makeDemo(undefined,port).flatMap(b=>b.containers), original=structuredClone(all);
    const fresh=all.find(c=>isPerishable(c)&&c.issue==='clear');
    assert.deepEqual(actionsFor(fresh,'routine'),[]);
    const action=actionsFor(fresh,'congestion')[0], exposure=congestionExposure(fresh,'congestion');
    assert.equal(action.issue,'congestion');assert.equal(action.quadrant,'do');
    assert.equal(exposure.delayMinutes,120);assert.equal(exposure.remainingMinutes,fresh.handlingWindowMinutes-120);
    assert.equal(priorityChange(fresh,'congestion').promoted,true);
    assert.equal(exceptionColor(fresh,'routine'),PERISHABLE_COLOR);
    assert.notEqual(exceptionColor(fresh,'congestion'),PERISHABLE_COLOR);
    const pharma=all.find(c=>c.cargo==='reefer'&&!isPerishable(c));
    assert.ok(pharma);assert.ok(!issuesFor(pharma,'congestion').includes('congestion'));
    assert.ok(!issuesFor({...fresh,yardStatus:'departed'},'congestion').length);
    assert.ok(!issuesFor({...fresh,verifiedAlternateAccess:true},'congestion').includes('congestion'));
    assert.deepEqual(all,original);
  }
});
test('perishable prerequisites rise and the queue respects urgency, importance and tighter windows', () => {
  const fresh=makeDemo().flatMap(b=>b.containers).find(c=>isPerishable(c));
  const held={...fresh,issue:'customs',handlingWindowMinutes:200};
  const normal=actionFor(held,'customs','routine'), congested=actionFor(held,'customs','congestion');
  assert.equal(normal.quadrant,'plan');assert.equal(congested.quadrant,'do');
  assert.ok(congested.importance>normal.importance&&congested.urgency>normal.urgency);
  assert.ok(issuesFor(held,'congestion').includes('customs'));
  const soon=actionFor({...fresh,handlingWindowMinutes:15},'congestion','congestion');
  const later=actionFor({...fresh,handlingWindowMinutes:100},'congestion','congestion');
  assert.ok(compareActions(soon,later)<0);
  const empty=makeDemo().find(b=>b.id==='C04').containers[0];
  assert.equal(actionFor(empty,'congestion','congestion').quadrant,'coordinate');
  assert.ok(compareActions(soon,actionFor(empty,'congestion','congestion'))<0);
});
