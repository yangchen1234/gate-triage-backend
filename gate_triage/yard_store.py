"""Transactional, per-browser yard workspaces backed by an actual SQLite database."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from math import floor
import json
from pathlib import Path
import secrets
import sqlite3
import time
from uuid import uuid4

from gate_triage.yard_data import PORTS, LABEL, POLICY_VERSION, issues_for, assess, make_yard, project


def encode(value): return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
def stamp(): return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


class YardError(Exception):
    def __init__(self, status, detail): self.status, self.detail = status, detail


SCHEMA = '''
CREATE TABLE IF NOT EXISTS yard_workspaces (
 id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, created REAL NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS yard_runs (
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL REFERENCES yard_workspaces(id) ON DELETE CASCADE,
 port TEXT NOT NULL CHECK(port IN ('la','rotterdam')), seed INTEGER NOT NULL,
 scenario TEXT NOT NULL, revision INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS yard_current_run ON yard_runs(workspace,port) WHERE active=1;
CREATE TABLE IF NOT EXISTS yard_blocks (
 run TEXT NOT NULL REFERENCES yard_runs(id) ON DELETE CASCADE, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(run,id));
CREATE TABLE IF NOT EXISTS yard_containers (
 run TEXT NOT NULL, id TEXT NOT NULL, block TEXT NOT NULL, bay INTEGER NOT NULL, row INTEGER NOT NULL,
 tier INTEGER NOT NULL, yard_status TEXT NOT NULL CHECK(yard_status IN ('in-yard','departed')),
 observation_version INTEGER NOT NULL DEFAULT 0, original_data TEXT NOT NULL, data TEXT NOT NULL,
 PRIMARY KEY(run,id), FOREIGN KEY(run,block) REFERENCES yard_blocks(run,id) ON DELETE CASCADE);
CREATE UNIQUE INDEX IF NOT EXISTS yard_occupied_slot ON yard_containers(run,block,bay,row,tier) WHERE yard_status='in-yard';
CREATE INDEX IF NOT EXISTS yard_inventory ON yard_containers(run,yard_status,block);
CREATE TABLE IF NOT EXISTS yard_jobs (
 run TEXT NOT NULL, key TEXT NOT NULL, container TEXT NOT NULL, issue TEXT NOT NULL, stage TEXT NOT NULL,
 data TEXT NOT NULL, PRIMARY KEY(run,key), FOREIGN KEY(run,container) REFERENCES yard_containers(run,id) ON DELETE CASCADE);
CREATE UNIQUE INDEX IF NOT EXISTS yard_open_case ON yard_jobs(run,container,issue) WHERE stage!='resolved';
CREATE TABLE IF NOT EXISTS yard_decisions (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT NOT NULL REFERENCES yard_runs(id) ON DELETE CASCADE, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS yard_resolutions (
 run TEXT NOT NULL, container TEXT NOT NULL, issue TEXT NOT NULL, data TEXT NOT NULL,
 PRIMARY KEY(run,container,issue), FOREIGN KEY(run,container) REFERENCES yard_containers(run,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS yard_departures (
 run TEXT NOT NULL, container TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(run,container),
 FOREIGN KEY(run,container) REFERENCES yard_containers(run,id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS yard_commands (
 workspace TEXT NOT NULL REFERENCES yard_workspaces(id) ON DELETE CASCADE, port TEXT NOT NULL,
 key TEXT NOT NULL, fingerprint TEXT NOT NULL, revision INTEGER NOT NULL, at TEXT NOT NULL,
 PRIMARY KEY(workspace,port,key));
CREATE TABLE IF NOT EXISTS yard_audit (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT NOT NULL REFERENCES yard_runs(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, type TEXT NOT NULL, at TEXT NOT NULL, container TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS yard_advisories (
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL REFERENCES yard_workspaces(id) ON DELETE CASCADE,
 run TEXT NOT NULL REFERENCES yard_runs(id) ON DELETE CASCADE, port TEXT NOT NULL,
 request_key TEXT NOT NULL, fingerprint TEXT NOT NULL, data TEXT NOT NULL,
 UNIQUE(workspace,port,request_key));
'''


class YardStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 3: raise RuntimeError('Yard database schema is newer than this application')
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0] < 3:
                at = stamp()
                for rid, revision in db.execute('SELECT id,revision FROM yard_runs WHERE active=1').fetchall():
                    db.execute('UPDATE yard_runs SET revision=?,updated_at=? WHERE id=?', (revision + 1, at, rid))
                    db.execute('INSERT INTO yard_audit(run,revision,type,at,data) VALUES (?,?,?,?,?)',
                               (rid, revision + 1, 'policy_upgrade', at, encode(dict(policyVersion=POLICY_VERSION, source='demo_profile_v2'))))
                db.execute('PRAGMA user_version=3')
            db.commit()
        finally:
            db.close()
        self.path.chmod(0o600)

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=5000')
        db.execute('PRAGMA synchronous=FULL')
        try:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            if db.in_transaction: db.commit()
        except Exception:
            if db.in_transaction: db.rollback()
            raise
        finally: db.close()

    @staticmethod
    def _hash(token): return sha256((token or '').encode()).hexdigest()

    def _workspace(self, db, token):
        if not token or len(token) > 128: raise YardError(401, 'Yard workspace expired or unavailable. Reconnect to continue.')
        row = db.execute('SELECT * FROM yard_workspaces WHERE token_hash=? AND expires>?', (self._hash(token), time.time())).fetchone()
        if not row: raise YardError(401, 'Yard workspace expired or unavailable. Reconnect to continue.')
        return row['id']

    def session(self, token=None):
        with self.connection(True) as db:
            now = time.time()
            try: workspace = self._workspace(db, token)
            except YardError: workspace = None
            if workspace:
                db.execute('UPDATE yard_workspaces SET expires=? WHERE id=?', (now + 604800, workspace))
            else:
                db.execute('DELETE FROM yard_workspaces WHERE expires<=?', (now,))
                if db.execute('SELECT count(*) FROM yard_workspaces').fetchone()[0] >= 100:
                    raise YardError(503, 'Yard demonstration capacity reached. Try again later.')
                workspace, token = str(uuid4()), secrets.token_urlsafe(32)
                db.execute('INSERT INTO yard_workspaces VALUES (?,?,?,?)', (workspace, self._hash(token), now, now + 604800))
            return token, dict(workspaceId=workspace, database='sqlite', persisted=True, synthetic=True, agentEnabled=False)

    def _new_run(self, db, workspace, port, seed=None, revision=1):
        rid, at = str(uuid4()), stamp()
        seed = PORTS[port]['seed'] if seed is None else seed
        db.execute('INSERT INTO yard_runs VALUES (?,?,?,?,?,?,?,?,?)', (rid, workspace, port, seed, 'routine', revision, 1, at, at))
        for b in make_yard(port, seed):
            rows = b.pop('containers')
            db.execute('INSERT INTO yard_blocks VALUES (?,?,?)', (rid, b['id'], encode(b)))
            db.executemany('INSERT INTO yard_containers VALUES (?,?,?,?,?,?,?,?,?,?)', [(rid, c['id'], c['block'], c['bay'], c['row'], c['tier'], 'in-yard', 0, encode(c), encode(c)) for c in rows])
        db.execute('INSERT INTO yard_audit(run,revision,type,at,data) VALUES (?,?,?,?,?)', (rid, revision, 'seed', at, encode(dict(seed=seed, port=port, source='yard_seed_v1'))))
        return db.execute('SELECT * FROM yard_runs WHERE id=?', (rid,)).fetchone()

    def _run(self, db, workspace, port):
        if port not in PORTS: raise YardError(404, 'Unknown yard port.')
        return db.execute('SELECT * FROM yard_runs WHERE workspace=? AND port=? AND active=1', (workspace, port)).fetchone()

    @staticmethod
    def etag(run): return f'"{run["id"]}:{run["revision"]}"'

    def snapshot(self, token, port, etag=None):
        # Seeding is the only write on first read, and is serialized by the database.
        with self.connection() as db:
            workspace = self._workspace(db, token)
            run = self._run(db, workspace, port)
            if run:
                if etag == self.etag(run): return None, etag
                return self._snapshot(db, run), self.etag(run)
        with self.connection(True) as db:
            workspace = self._workspace(db, token)
            run = self._run(db, workspace, port) or self._new_run(db, workspace, port)
            return self._snapshot(db, run), self.etag(run)

    def _records(self, db, table, rid):
        order = 'seq DESC' if table == 'yard_decisions' else 'rowid DESC'
        return [json.loads(r['data']) for r in db.execute(f'SELECT data FROM {table} WHERE run=? ORDER BY {order}', (rid,))]

    def _snapshot(self, db, run):
        rid, scenario = run['id'], run['scenario']
        fixed = self._records(db, 'yard_resolutions', rid)
        departures = self._records(db, 'yard_departures', rid)
        jobs = self._records(db, 'yard_jobs', rid)
        catalog = []
        for row in db.execute('SELECT * FROM yard_containers WHERE run=? ORDER BY id', (rid,)):
            c = project(json.loads(row['data']), fixed, row['yard_status'] == 'departed')
            c['observationVersion'] = row['observation_version']
            c['assessments'] = {s: [assess(c, issue, s) for issue in issues_for(c, s)] for s in {scenario, 'routine'}}
            catalog.append(c)
        by_block = {}
        for c in catalog:
            if c['yardStatus'] == 'in-yard': by_block.setdefault(c['block'], []).append(c)
        blocks = [dict(json.loads(r['data']), containers=by_block.get(r['id'], [])) for r in db.execute('SELECT id,data FROM yard_blocks WHERE run=? ORDER BY rowid', (rid,))]
        run_data = dict(version=1, port=run['port'], seed=run['seed'], decisions=self._records(db, 'yard_decisions', rid), jobs=jobs, resolutions=fixed, departures=departures)
        return dict(workspaceId=run['workspace'], runId=rid, revision=run['revision'], scenario=scenario, updatedAt=run['updated_at'], run=run_data,
                    blocks=blocks, catalog=catalog, database='sqlite', persisted=True, synthetic=True, policyVersion=POLICY_VERSION, agentEnabled=False)

    def command(self, token, port, event, expected, key):
        fingerprint = sha256(encode(dict(event=event, expected=expected)).encode()).hexdigest()
        with self.connection(True) as db:
            workspace = self._workspace(db, token)
            run = self._run(db, workspace, port)
            if not run: raise YardError(409, 'Load the yard before changing it.')
            prior = db.execute('SELECT * FROM yard_commands WHERE workspace=? AND port=? AND key=?', (workspace, port, key)).fetchone()
            if prior:
                if prior['fingerprint'] != fingerprint: raise YardError(409, 'This request key was already used for a different operation.')
                return self._snapshot(db, run), self.etag(run)
            if expected != self.etag(run): raise YardError(412, 'The yard changed. Current data has been refreshed; review the action before trying again.')
            at = stamp()
            if event['type'] == 'reset':
                if db.execute('SELECT count(*) FROM yard_runs WHERE workspace=?', (workspace,)).fetchone()[0] >= 40:
                    raise YardError(429, 'Demo reset limit reached for this workspace.')
                db.execute('UPDATE yard_runs SET active=0 WHERE id=?', (run['id'],))
                run = self._new_run(db, workspace, port, (run['seed'] + 1) & 0xffffffff, run['revision'] + 1)
            else:
                self._apply(db, run, event, at)
                db.execute('UPDATE yard_runs SET revision=revision+1,updated_at=? WHERE id=?', (at, run['id']))
                run = db.execute('SELECT * FROM yard_runs WHERE id=?', (run['id'],)).fetchone()
            db.execute('INSERT INTO yard_audit(run,revision,type,at,container,data) VALUES (?,?,?,?,?,?)', (run['id'], run['revision'], event['type'], at, event.get('containerId'), encode(event)))
            db.execute('INSERT INTO yard_commands VALUES (?,?,?,?,?,?)', (workspace, port, key, fingerprint, run['revision'], at))
            return self._snapshot(db, run), self.etag(run)

    def _apply(self, db, run, event, at):
        rid, kind, scenario = run['id'], event['type'], run['scenario']
        if kind == 'scenario':
            db.execute('UPDATE yard_runs SET scenario=? WHERE id=?', (event['scenario'], rid))
            return
        if kind in ('review', 'gate_out', 'observe'):
            row = db.execute('SELECT * FROM yard_containers WHERE run=? AND id=?', (rid, event['containerId'])).fetchone()
            if not row: raise YardError(404, 'Container not found in this yard run.')
            if row['yard_status'] != 'in-yard': raise YardError(409, 'This container has already gated out. No second slot can be released.')
            raw = json.loads(row['data'])
            c = project(raw, self._records(db, 'yard_resolutions', rid))
            if kind == 'observe':
                issue = event['issue']
                if issue in ('temperature', 'sensor') and c['cargo'] != 'reefer': raise YardError(422, 'This observation requires a refrigerated container.')
                if issue == 'temperature': raw['temperature'] = raw['setpoint'] + 5.8
                if issue == 'sensor': raw['reported'] = 125
                if issue == 'weight': raw['declared'] = floor(raw['weight'] * .54 + .5)
                raw['extraIssues'] = sorted(set(raw.get('extraIssues', [])) | {issue})
                raw.update(lastObservedAt=at, lastObservedSource='demo_simulator')
                db.execute('UPDATE yard_containers SET data=?,observation_version=observation_version+1 WHERE run=? AND id=?', (encode(raw), rid, c['id']))
                db.execute('DELETE FROM yard_resolutions WHERE run=? AND container=? AND issue=?', (rid, c['id'], issue))
                # New measurements invalidate an unverified completion; old resolved
                # cases remain audited and a recurrence needs a new acceptance.
                open_job = db.execute("SELECT data FROM yard_jobs WHERE run=? AND container=? AND issue=? AND stage!='resolved'", (rid, c['id'], issue)).fetchone()
                if open_job:
                    job = json.loads(open_job['data'])
                    if job['stage'] == 'awaiting_verification': job.update(stage='in_progress', workNote='', evidence='')
                    job['updatedAt'] = at
                    job['events'].append(dict(stage=job['stage'], at=at, note='New observation requires another check.'))
                    self._save_job(db, rid, job)
                return
            if event['scenario'] != scenario: raise YardError(409, 'The scenario changed. Refresh before reviewing this action.')
            open_jobs = db.execute("SELECT data FROM yard_jobs WHERE run=? AND container=? AND stage!='resolved'", (rid, c['id'])).fetchall()
            if kind == 'gate_out':
                if issues_for(c, scenario) or open_jobs: raise YardError(409, 'Resolve every active exception and finish accepted work before release and gate-out.')
                if not event['clearanceConfirmed'] or not event['exitConfirmed']: raise YardError(422, 'Confirm both release permissions and physical gate-out. Clearance alone does not free a slot.')
                data = dict(containerId=c['id'], scenario=scenario, at=at, evidence=event['evidence'], block=c['block'], bay=c['bay'], row=c['row'], tier=c['tier'], plugId=c['plug']['id'] if c['plug'] else None)
                db.execute('INSERT INTO yard_departures VALUES (?,?,?)', (rid, c['id'], encode(data)))
                db.execute("UPDATE yard_containers SET yard_status='departed' WHERE run=? AND id=?", (rid, c['id']))
                return
            issue = event['issue']
            if issue not in issues_for(c, scenario): raise YardError(409, 'This exception is no longer active. Refresh the selected action.')
            if any(json.loads(j['data'])['issue'] == issue for j in open_jobs): raise YardError(409, 'This action is already in the post-action workflow.')
            decision = dict(id=c['id'], scenario=scenario, issue=issue, choice=event['choice'], note=event['note'], at=at, observationVersion=row['observation_version'])
            db.execute('INSERT INTO yard_decisions(run,data) VALUES (?,?)', (rid, encode(decision)))
            if event['choice'] == 'accepted':
                job = dict(key=f"{c['id']}:{issue}:{row['observation_version']}", containerId=c['id'], issue=issue, scenario=scenario,
                           stage='queued', createdAt=at, updatedAt=at, note=event['note'], workNote='', evidence='',
                           events=[dict(stage='queued', at=at, note=event['note'] or 'Suggestion accepted')])
                db.execute('INSERT INTO yard_jobs VALUES (?,?,?,?,?,?)', (rid, job['key'], c['id'], issue, 'queued', encode(job)))
            return
        job_row = db.execute('SELECT data FROM yard_jobs WHERE run=? AND key=?', (rid, event['key'])).fetchone()
        if not job_row: raise YardError(404, 'Post-action task not found.')
        job = json.loads(job_row['data'])
        required = {'start': 'queued', 'complete_work': 'in_progress', 'verify': 'awaiting_verification'}[kind]
        if job['stage'] != required: raise YardError(409, 'Task stage changed. Refresh its current state before continuing.')
        if kind == 'start': job.update(stage='in_progress'); note = 'Work started'
        elif kind == 'complete_work': job.update(stage='awaiting_verification', workNote=event['note']); note = event['note']
        else:
            if not event['confirmed']: raise YardError(422, 'Confirm the result and add its evidence reference before resolving.')
            job.update(stage='resolved', evidence=event['evidence']); note = event['evidence']
            result = dict(containerId=job['containerId'], issue=job['issue'], evidence=event['evidence'], at=at)
            db.execute('INSERT OR REPLACE INTO yard_resolutions VALUES (?,?,?,?)', (rid, job['containerId'], job['issue'], encode(result)))
        job['updatedAt'] = at
        job['events'].append(dict(stage=job['stage'], at=at, note=note))
        self._save_job(db, rid, job)

    @staticmethod
    def _save_job(db, rid, job):
        db.execute('UPDATE yard_jobs SET stage=?,data=? WHERE run=? AND key=?', (job['stage'], encode(job), rid, job['key']))

    def audit(self, token, port, limit=100):
        with self.connection() as db:
            workspace = self._workspace(db, token)
            run = self._run(db, workspace, port)
            if not run: return []
            return [dict(id=r['seq'], runId=r['run'], revision=r['revision'], type=r['type'], at=r['at'], containerId=r['container'], data=json.loads(r['data'])) for r in db.execute('SELECT a.* FROM yard_audit a JOIN yard_runs r ON r.id=a.run WHERE r.workspace=? AND r.port=? ORDER BY a.seq DESC LIMIT ?', (workspace, port, limit))]

    def reserve_advisory(self, token, port, event, expected, key, build_context):
        fingerprint = sha256(encode(dict(event=event, expected=expected)).encode()).hexdigest()
        with self.connection(True) as db:
            workspace = self._workspace(db, token)
            prior = db.execute('SELECT data,fingerprint FROM yard_advisories WHERE workspace=? AND port=? AND request_key=?', (workspace, port, key)).fetchone()
            if prior:
                if prior['fingerprint'] != fingerprint: raise YardError(409, 'This request key belongs to a different advisory.')
                return self._advisory_view(db, json.loads(prior['data'])), False
            run = self._run(db, workspace, port)
            if not run or expected != self.etag(run): raise YardError(412, 'The yard changed. Refresh before asking Claude.')
            if db.execute('SELECT count(*) FROM yard_advisories WHERE workspace=?', (workspace,)).fetchone()[0] >= 24:
                raise YardError(429, 'Advisory history limit reached for this demo workspace.')
            context = build_context(self._snapshot(db, run), event)
            job = dict(id=str(uuid4()), requestId=key, runId=run['id'], inputRevision=run['revision'], port=port,
                       containerId=event['containerId'], issue=event['issue'], question=event['question'],
                       status='running', createdAt=stamp(), completedAt=None, result=None, error=None, context=context)
            db.execute('INSERT INTO yard_advisories VALUES (?,?,?,?,?,?,?)', (job['id'], workspace, run['id'], port, key, fingerprint, encode(job)))
            return self._advisory_view(db, job), True

    def _advisory_view(self, db, data):
        current = db.execute('SELECT id,revision FROM yard_runs WHERE workspace=(SELECT workspace FROM yard_runs WHERE id=?) AND port=? AND active=1', (data['runId'], data['port'])).fetchone()
        return dict(data, stale=not current or current['id'] != data['runId'] or current['revision'] != data['inputRevision'])

    def advisory(self, token, port, job_id):
        with self.connection() as db:
            workspace = self._workspace(db, token)
            row = db.execute('SELECT data FROM yard_advisories WHERE workspace=? AND port=? AND id=?', (workspace, port, job_id)).fetchone()
            if not row: raise YardError(404, 'Advisory not found in this workspace.')
            return self._advisory_view(db, json.loads(row['data']))

    def latest_advisory(self, token, port, container_id, issue):
        with self.connection() as db:
            workspace = self._workspace(db, token)
            run = self._run(db, workspace, port)
            if not run: return None
            for row in db.execute('SELECT data FROM yard_advisories WHERE workspace=? AND port=? AND run=? ORDER BY rowid DESC', (workspace, port, run['id'])):
                data = json.loads(row['data'])
                if data['containerId'] == container_id and data['issue'] == issue:
                    return self._advisory_view(db, data)
            return None

    def finish_advisory(self, job_id, result=None, error=None):
        with self.connection(True) as db:
            row = db.execute('SELECT data FROM yard_advisories WHERE id=?', (job_id,)).fetchone()
            if not row: return
            job = json.loads(row['data'])
            if job['status'] != 'running': return
            job.update(status='failed' if error else 'succeeded', result=result, error=error, completedAt=stamp())
            db.execute('UPDATE yard_advisories SET data=? WHERE id=?', (encode(job), job_id))

    def interrupt_advisories(self):
        # A restart must never silently repeat a potentially paid request.
        with self.connection(True) as db:
            for row in db.execute('SELECT id,data FROM yard_advisories').fetchall():
                job = json.loads(row['data'])
                if job['status'] == 'running':
                    job.update(status='failed', error='Generation was interrupted by a server restart. Generate again explicitly.', completedAt=stamp())
                    db.execute('UPDATE yard_advisories SET data=? WHERE id=?', (encode(job), row['id']))
