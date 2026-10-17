import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { clearSession, markWorkspaceUnavailable, recentWorkspaces, saveRecentWorkspace, saveSession, savedSession } from '../src/api.ts';

beforeEach(() => {
  const values = new Map();
  globalThis.localStorage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key),
  };
});

test('creating a new rehearsal retains every previous workspace access record', () => {
  saveSession('first', 'first-local-access', { name: 'First rehearsal', scenario_name: 'Everyday operations', clock_min: 45 });
  saveSession('second', 'second-local-access', { name: 'Second rehearsal', scenario_name: 'Access disruption', clock_min: 0 });
  assert.equal(savedSession().id, 'second');
  assert.equal(recentWorkspaces().length, 2);
  assert.equal(recentWorkspaces().find(item => item.id === 'first').clock_min, 45);
  assert.equal(recentWorkspaces().find(item => item.id === 'first').token, 'first-local-access');
});

test('marking one unavailable does not remove other rehearsal access', () => {
  saveSession('first', 'first-local-access');
  saveSession('second', 'second-local-access');
  markWorkspaceUnavailable('second');
  saveSession('third', 'third-local-access');
  assert.equal(recentWorkspaces().find(item => item.id === 'second').unavailable, true);
  assert.equal(recentWorkspaces().find(item => item.id === 'first').token, 'first-local-access');
  assert.equal(recentWorkspaces().length, 3);
});

test('resuming updates metadata and active context without duplicating entries', () => {
  saveSession('first', 'first-local-access', { clock_min: 15 });
  saveSession('second', 'second-local-access');
  saveSession('first', 'first-local-access', { clock_min: 90 });
  assert.equal(savedSession().id, 'first');
  assert.equal(recentWorkspaces().length, 2);
  assert.equal(recentWorkspaces().find(item => item.id === 'first').clock_min, 90);
  clearSession();
  assert.equal(savedSession(), null);
  assert.equal(recentWorkspaces().length, 2);
});

test('an older single-session record is migrated before it is replaced', () => {
  localStorage.setItem('gate-triage-session-v1', JSON.stringify({ id: 'legacy', token: 'legacy-local-access' }));
  saveSession('new', 'new-local-access');
  assert.equal(recentWorkspaces().find(item => item.id === 'legacy').token, 'legacy-local-access');
  saveRecentWorkspace('legacy', 'legacy-local-access', { name: 'Recovered legacy rehearsal' });
  assert.equal(recentWorkspaces().length, 2);
});
