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
def test_shared_congestion_reaches_scattered_perishables_without_area_closures(port):
    rows = cohort(port)
    perishable = [c for c in rows if c['perishable']]
    assert perishable and any(c['cargo'] == 'reefer' and not c['perishable'] for c in rows)
    assert len({c['block'] for c in perishable}) >= (8 if port == 'la' else 6)
    ambient = [c for c in perishable if c['cargo'] == 'dry']
    assert ambient and all(c['plug'] is None and c['commodity'] == 'Ambient produce' for c in ambient)
    for c in rows:
        expected = c['perishable']
        assert ('congestion' in issues_for(c, 'congestion')) == expected
        exposure = congestion_exposure(c, 'congestion')
        assert exposure['affected'] and exposure['route'] == 'YARD-EXIT'
        assert exposure['delayDays'] == 1
        assert isinstance(exposure['windowDays'], int) and exposure['windowDays'] >= 1
        assert isinstance(exposure['remainingDays'], int)
        if c['cargo'] in ('empty', 'hazmat'): assert not c['perishable']
    assert all('congestion' not in issues_for(c, 'routine') for c in rows)


def test_delay_margin_and_prerequisite_scores_rise_without_clearing_controls():
    c = deepcopy(next(c for c in cohort() if c['perishable'] and c['cargo'] == 'reefer' and c['issue'] == 'clear'))
    c.update(issue='customs', pickupWindowDays=3)
    original = deepcopy(c)
    routine, blocked = assess(c, 'customs', 'routine'), assess(c, 'customs', 'congestion')
    assert routine['quadrant'] == 'plan' and blocked['quadrant'] == 'do'
    assert blocked['importance'] > routine['importance'] and blocked['urgency'] > routine['urgency']
    for issue in ('weight', 'sensor'):
        assert assess(c, issue, 'congestion')['urgency'] > assess(c, issue, 'routine')['urgency']
    urgencies = [assess({**c, 'pickupWindowDays': window}, 'congestion', 'congestion')['urgency'] for window in (5, 4, 2, 1)]
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
    assert 'congestion' not in issues_for(empty, 'congestion')
    assert assess(fresh, 'congestion', 'congestion')['quadrant'] == 'do'


@pytest.mark.parametrize('previous_version', [2, 3])
def test_upgrade_preserves_originals_workflows_and_invalidates_old_etag_once(tmp_path, previous_version):
    path = tmp_path / 'upgrade.sqlite3'
    store = YardStore(path)
    token, _ = store.session()
    before, etag = store.snapshot(token, 'la')
    cid = next(c['id'] for c in before['catalog'] if c['perishable'])
    with sqlite3.connect(path) as db:
        raw = json.loads(db.execute('SELECT data FROM yard_containers WHERE id=?', (cid,)).fetchone()[0])
        for key in cargo_profile(raw): raw.pop(key, None)
        db.execute('UPDATE yard_containers SET data=?,original_data=? WHERE id=?', (json.dumps(raw), json.dumps(raw), cid))
        db.execute(f'PRAGMA user_version={previous_version}')
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
