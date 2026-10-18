import { ISSUE, issuesFor, makeDemo, PORTS } from './yard-demo.ts';
import type { DemoBlock, DemoContainer, DemoDecision, DemoPort, DemoScenario, Issue } from './yard-demo.ts';

export type WorkIssue = Exclude<Issue, 'clear'>;
export type WorkStage = 'queued' | 'in_progress' | 'awaiting_verification' | 'resolved';
export type WorkEvent = { stage: WorkStage; at: string; note: string };
export type PostActionJob = {
  key: string; containerId: string; issue: WorkIssue; scenario: DemoScenario;
  stage: WorkStage; createdAt: string; updatedAt: string; note: string;
  workNote: string; evidence: string; events: WorkEvent[];
};
export type Resolution = { containerId: string; issue: WorkIssue; evidence: string; at: string };
export type Departure = { containerId: string; scenario: DemoScenario; at: string; evidence: string; block: string; bay: number; row: number; tier: number; plugId: string | null };
export type YardRun = { version: 1; port: DemoPort; seed: number; decisions: DemoDecision[]; jobs: PostActionJob[]; resolutions: Resolution[]; departures: Departure[] };
export type WorkflowEvent =
  | { type: 'review'; containerId: string; issue: WorkIssue; scenario: DemoScenario; choice: DemoDecision['choice']; note: string; at: string }
  | { type: 'start'; key: string; at: string }
  | { type: 'complete_work'; key: string; note: string; at: string }
  | { type: 'verify'; key: string; evidence: string; confirmed: boolean; at: string }
  | { type: 'gate_out'; containerId: string; scenario: DemoScenario; evidence: string; clearanceConfirmed: boolean; exitConfirmed: boolean; at: string };
export const WORK_STAGE: Record<WorkStage, { label: string; detail: string }> = {
  queued: { label: 'Queued', detail: 'Accepted · waiting for work to start' },
  in_progress: { label: 'In progress', detail: 'Work started · exception remains active' },
  awaiting_verification: { label: 'Verify result', detail: 'Work reported complete · evidence required' },
  resolved: { label: 'Resolved', detail: 'Verified · container remains in yard until gate-out' },
};
export const VERIFICATION: Record<WorkIssue, string> = {
  customs: 'The responsible authority’s clearance has been confirmed for this container.',
  weight: 'Container identity and weighing basis were checked; the verified weight now agrees with the corrected record.',
  temperature: 'A verified reading is back at the required setpoint for this demo container.',
  sensor: 'Fresh telemetry and the actual unit condition have been verified.',
  power: 'Backup power for this specific unit has been verified. This does not restore the entire R1 circuit.',
  congestion: 'An authorized, usable alternate pickup access has been confirmed for this specific container.',
};
export function createYardRun(seed?: number, port: DemoPort = 'la'): YardRun { return { version: 1, port, seed: seed ?? PORTS[port].seed, decisions: [], jobs: [], resolutions: [], departures: [] }; }
export const workKey = (containerId: string, issue: WorkIssue) => `${containerId}:${issue}`;

export function projectContainer(c: DemoContainer, run: YardRun): DemoContainer {
  const resolved = new Set(run.resolutions.filter(r => r.containerId === c.id).map(r => r.issue));
  return {
    ...c, yardStatus: run.departures.some(d => d.containerId === c.id) ? 'departed' : c.yardStatus,
    issue: c.issue !== 'clear' && resolved.has(c.issue) ? 'clear' : c.issue,
    declared: resolved.has('weight') ? c.weight : c.declared,
    temperature: resolved.has('temperature') ? c.setpoint : c.temperature,
    reported: resolved.has('sensor') ? 0 : c.reported,
    verifiedUnitBackup: resolved.has('power'), verifiedAlternateAccess: resolved.has('congestion'),
  };
}
export function projectYard(blocks: DemoBlock[], run: YardRun): DemoBlock[] {
  return blocks.map(b => ({ ...b, containers: b.containers.map(c => projectContainer(c, run)).filter(c => c.yardStatus === 'in-yard') }));
}
export function releaseBlockers(c: DemoContainer, run: YardRun, scenario: DemoScenario): string[] {
  return [
    ...issuesFor(c, scenario).map(i => ISSUE[i].label),
    ...run.jobs.filter(j => j.containerId === c.id && j.stage !== 'resolved').map(j => `${ISSUE[j.issue].short}: ${WORK_STAGE[j.stage].label}`),
  ];
}
type Transition = { ok: true; run: YardRun } | { ok: false; error: string };
const fail = (error: string): Transition => ({ ok: false, error });
export function transitionWorkflow(run: YardRun, event: WorkflowEvent, baseBlocks: DemoBlock[] = makeDemo(run.seed, run.port)): Transition {
  if (!Number.isFinite(Date.parse(event.at))) return fail('A valid event time is required.');
  const source = baseBlocks.flatMap(b => b.containers);
  if (event.type === 'review' || event.type === 'gate_out') {
    const base = source.find(c => c.id === event.containerId);
    if (!base) return fail('Container not found in this demo run.');
    const c = projectContainer(base, run);
    if (c.yardStatus !== 'in-yard') return fail('This container has already gated out. No second slot can be released.');
    if (event.type === 'review') {
      if (!issuesFor(c, event.scenario).includes(event.issue)) return fail('This exception is no longer active. Refresh the selected action.');
      if (run.jobs.some(j => j.key === workKey(c.id, event.issue))) return fail('This action is already in the post-action workflow.');
      const decision: DemoDecision = { id: c.id, scenario: event.scenario, issue: event.issue, choice: event.choice, note: event.note.trim(), at: event.at };
      const decisions = [decision, ...run.decisions.filter(d => !(d.id === c.id && d.issue === event.issue && d.scenario === event.scenario))];
      const job: PostActionJob = { key: workKey(c.id, event.issue), containerId: c.id, issue: event.issue, scenario: event.scenario, stage: 'queued', createdAt: event.at, updatedAt: event.at, note: event.note.trim(), workNote: '', evidence: '', events: [{ stage: 'queued', at: event.at, note: event.note.trim() || 'Suggestion accepted' }] };
      return { ok: true, run: { ...run, decisions, jobs: event.choice === 'accepted' ? [job, ...run.jobs] : run.jobs } };
    }
    if (releaseBlockers(c, run, event.scenario).length) return fail('Resolve every active exception and finish accepted work before release and gate-out.');
    if (!event.clearanceConfirmed || !event.exitConfirmed) return fail('Confirm both release permissions and physical gate-out. Clearance alone does not free a slot.');
    if (event.evidence.trim().length < 3) return fail('Add a gate-out reference or confirmation note.');
    const departure: Departure = { containerId: c.id, scenario: event.scenario, at: event.at, evidence: event.evidence.trim(), block: c.block, bay: c.bay, row: c.row, tier: c.tier, plugId: c.plug?.id || null };
    return { ok: true, run: { ...run, departures: [departure, ...run.departures] } };
  }
  const job = run.jobs.find(j => j.key === event.key);
  if (!job) return fail('Post-action task not found.');
  if (Date.parse(event.at) < Date.parse(job.updatedAt)) return fail('This update predates the latest task event. Refresh and try again.');
  if (run.departures.some(d => d.containerId === job.containerId)) return fail('This container has already left the yard.');
  let updated: PostActionJob;
  if (event.type === 'start') {
    if (job.stage !== 'queued') return fail('Only queued tasks can be started.');
    updated = { ...job, stage: 'in_progress', updatedAt: event.at, events: [...job.events, { stage: 'in_progress', at: event.at, note: 'Work started' }] };
  } else if (event.type === 'complete_work') {
    if (job.stage !== 'in_progress') return fail('Start the work before reporting completion.');
    if (event.note.trim().length < 3) return fail('Add a short work-completion summary.');
    updated = { ...job, stage: 'awaiting_verification', updatedAt: event.at, workNote: event.note.trim(), events: [...job.events, { stage: 'awaiting_verification', at: event.at, note: event.note.trim() }] };
  } else {
    if (job.stage !== 'awaiting_verification') return fail('Only completed work awaiting verification can be resolved.');
    if (!event.confirmed || event.evidence.trim().length < 3) return fail('Confirm the result and add its evidence reference before resolving.');
    updated = { ...job, stage: 'resolved', updatedAt: event.at, evidence: event.evidence.trim(), events: [...job.events, { stage: 'resolved', at: event.at, note: event.evidence.trim() }] };
  }
  return { ok: true, run: {
    ...run, jobs: run.jobs.map(j => j.key === job.key ? updated : j),
    resolutions: updated.stage === 'resolved' ? [...run.resolutions, { containerId: job.containerId, issue: job.issue, evidence: updated.evidence, at: event.at }] : run.resolutions,
  } };
}

const STORAGE_KEYS: Record<DemoPort, string> = { la: 'gate-triage-yard-workflow:v1', rotterdam: 'gate-triage-yard-workflow:rotterdam:v1' };
const isRecord = (v: unknown): v is Record<string, unknown> => Boolean(v) && typeof v === 'object' && !Array.isArray(v);
const validIssue = (v: unknown): v is WorkIssue => typeof v === 'string' && v !== 'clear' && Object.hasOwn(ISSUE, v);
const validTime = (v: unknown) => typeof v === 'string' && Number.isFinite(Date.parse(v));
const validScenario = (v: unknown) => ['routine', 'power', 'congestion', 'combined'].includes(String(v));
// Saved data is local, synthetic and versioned. Validate before restoring any occupancy change.
export function parseYardRun(raw: string | null): YardRun | null {
  if (!raw) return null;
  try {
    const v: unknown = JSON.parse(raw);
    if (!isRecord(v) || v.version !== 1 || !Number.isInteger(v.seed) || Number(v.seed) < 0 || Number(v.seed) > 0xffffffff) return null;
    for (const key of ['decisions', 'jobs', 'resolutions', 'departures']) if (!Array.isArray(v[key]) || (v[key] as unknown[]).length > 20000) return null;
    if (v.port !== undefined && v.port !== 'la' && v.port !== 'rotterdam') return null;
    const run = { ...v, port: v.port || 'la' } as unknown as YardRun, base = makeDemo(run.seed, run.port).flatMap(b => b.containers), ids = new Set(base.map(c => c.id));
    if (!run.decisions.every(d => isRecord(d) && ids.has(d.id) && validScenario(d.scenario) && validIssue(d.issue) && ['accepted', 'dismissed'].includes(d.choice) && typeof d.note === 'string' && validTime(d.at))) return null;
    if (!run.jobs.every(j => isRecord(j) && ids.has(j.containerId) && validIssue(j.issue) && j.key === workKey(j.containerId, j.issue) && validScenario(j.scenario) && Object.hasOwn(WORK_STAGE, j.stage) && validTime(j.createdAt) && validTime(j.updatedAt) && typeof j.note === 'string' && typeof j.workNote === 'string' && typeof j.evidence === 'string' && Array.isArray(j.events) && j.events.length > 0 && j.events.every(e => isRecord(e) && Object.hasOwn(WORK_STAGE, e.stage) && validTime(e.at) && typeof e.note === 'string'))) return null;
    if (new Set(run.jobs.map(j => j.key)).size !== run.jobs.length) return null;
    if (!run.resolutions.every(r => isRecord(r) && ids.has(r.containerId) && validIssue(r.issue) && typeof r.evidence === 'string' && r.evidence.trim().length >= 3 && validTime(r.at) && run.jobs.some(j => j.key === workKey(r.containerId, r.issue) && j.stage === 'resolved' && j.evidence === r.evidence))) return null;
    if (new Set(run.resolutions.map(r => workKey(r.containerId, r.issue))).size !== run.resolutions.length) return null;
    if (run.jobs.some(j => j.stage === 'resolved' && !run.resolutions.some(r => workKey(r.containerId, r.issue) === j.key))) return null;
    if (!run.departures.every(d => { if (!isRecord(d)) return false; const c = base.find(c => c.id === d.containerId); return c && validScenario(d.scenario) && d.block === c.block && d.bay === c.bay && d.row === c.row && d.tier === c.tier && d.plugId === (c.plug?.id || null) && typeof d.evidence === 'string' && d.evidence.trim().length >= 3 && validTime(d.at) && !releaseBlockers(projectContainer(c, { ...run, departures: [] }), run, d.scenario).length; })) return null;
    if (new Set(run.departures.map(d => d.containerId)).size !== run.departures.length) return null;
    return run;
  } catch { return null; }
}
export function loadYardRun(port: DemoPort = 'la'): YardRun { try { const run = parseYardRun(window.localStorage.getItem(STORAGE_KEYS[port])); return run?.port === port ? run : createYardRun(undefined, port); } catch { return createYardRun(undefined, port); } }
export function saveYardRun(run: YardRun): boolean { try { window.localStorage.setItem(STORAGE_KEYS[run.port], JSON.stringify(run)); return true; } catch { return false; } }
