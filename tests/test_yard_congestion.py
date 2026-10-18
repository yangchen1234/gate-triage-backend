"""Congestion reprioritizes real demo records, without inventing permission or spoilage."""
from copy import deepcopy
import json
import sqlite3

import pytest

from gate_triage.yard_data import make_yard, issues_for, assess, project, cargo_profile, congestion_exposure
from gate_triage.yard_store import YardStore, YardError


def cohort(port='la'):
    return [c for b in make_yard(port) for c in b['containers']]


@pytest.mark.parametrize('port', ['la', 'rotterdam'])
def test_congestion_reaches_dependent_perishables_not_every_reefer_or_export(port):
    rows = cohort(port)
    perishable = [c for c in rows if c['perishable']]
    assert perishable and any(c['cargo'] == 'reefer' and not c['perishable'] for c in rows)
    assert {c['block'] for c in perishable} == {'B01', 'B02', 'C01'}
    for c in rows:
        expected = c['block'] in ('C03', 'C04') or c['perishable']
        assert ('congestion' in issues_for(c, 'congestion')) == expected
        if c['block'] in ('A03', 'A04', 'B03', 'B04', 'C02'):
            assert not congestion_exposure(c, 'congestion')['affected']
    assert all('congestion' not in issues_for(c, 'routine') for c in rows)


def test_delay_margin_and_prerequisite_scores_rise_without_clearing_controls():
    c = deepcopy(next(c for c in cohort() if c['perishable'] and c['issue'] == 'clear'))
    c.update(issue='customs', handlingWindowMinutes=200)
    original = deepcopy(c)
    routine, blocked = assess(c, 'customs', 'routine'), assess(c, 'customs', 'congestion')
    assert routine['quadrant'] == 'plan' and blocked['quadrant'] == 'do'
    assert blocked['importance'] > routine['importance'] and blocked['urgency'] > routine['urgency']
    for issue in ('weight', 'sensor'):
        assert assess(c, issue, 'congestion')['urgency'] > assess(c, issue, 'routine')['urgency']
    urgencies = [assess({**c, 'handlingWindowMinutes': window}, 'congestion', 'congestion')['urgency'] for window in (360, 300, 180, 120, 15)]
    assert urgencies == sorted(urgencies) and urgencies[-1] < assess(c, 'power', 'combined')['urgency']
    assert c == original and 'customs' in issues_for(c, 'congestion')
    fixed = project(c, [dict(containerId=c['id'], issue='congestion')])
    assert issues_for(fixed, 'congestion') == ['customs']
    assert not congestion_exposure(fixed, 'congestion')['affected']
    assert 'congestion' in issues_for(next(c for c in cohort() if c['perishable'] and c['id'] != fixed['id']), 'congestion')


def test_empty_repositioning_does_not_outrank_perishable_pickup():
    rows = cohort()
    empty = next(c for c in rows if c['block'] == 'C04')
    fresh = next(c for c in rows if c['perishable'])
    assert assess(empty, 'congestion', 'congestion')['quadrant'] == 'coordinate'
    assert assess(fresh, 'congestion', 'congestion')['quadrant'] == 'do'


def test_upgrade_preserves_originals_workflows_and_invalidates_old_etag_once(tmp_path):
    path = tmp_path / 'upgrade.sqlite3'
    store = YardStore(path)
    token, _ = store.session()
    before, etag = store.snapshot(token, 'la')
    cid = next(c['id'] for c in before['catalog'] if c['perishable'])
    with sqlite3.connect(path) as db:
        raw = json.loads(db.execute('SELECT data FROM yard_containers WHERE id=?', (cid,)).fetchone()[0])
        for key in cargo_profile(raw): raw.pop(key, None)
        db.execute('UPDATE yard_containers SET data=?,original_data=? WHERE id=?', (json.dumps(raw), json.dumps(raw), cid))
        db.execute('PRAGMA user_version=2')
    upgraded = YardStore(path)
    after, fresh_etag = upgraded.snapshot(token, 'la', etag)
    assert after['runId'] == before['runId'] and after['revision'] == before['revision'] + 1
    assert len(after['catalog']) == len(before['catalog']) and after['run'] == before['run']
    assert next(c for c in after['catalog'] if c['id'] == cid)['perishable'] is True
    with sqlite3.connect(path) as db:
        assert json.loads(db.execute('SELECT original_data FROM yard_containers WHERE id=?', (cid,)).fetchone()[0]) == raw
        assert db.execute("SELECT count(*) FROM yard_audit WHERE type='policy_upgrade'").fetchone()[0] == 1
    with pytest.raises(YardError) as err:
        upgraded.command(token, 'la', dict(type='scenario', scenario='congestion'), etag, 'old-version-request')
    assert err.value.status == 412
    restarted = YardStore(path)
    assert restarted.snapshot(token, 'la', fresh_etag)[0] is None
