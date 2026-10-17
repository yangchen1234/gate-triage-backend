import { Activity, Anchor, ArrowRight, Check, ChevronRight, CircleHelp, Globe2, KeyRound, Layers3, LayoutDashboard, LoaderCircle, RefreshCw, Settings2, ShieldCheck, Sparkles, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, loadSession, newSession } from './api.ts';
import type { Container, Job, ModelStatus, PlanAction, Port, PortCode, Scenario, Snapshot } from './types.ts';
import { dateTime, jobIsRunning, mergeJob, preferredPlanId, requestIntent } from './state.ts';
import type { RequestIntent } from './state.ts';
import { Badge, EvidenceDrawer } from './Components.tsx';
import Operations from './Operations.tsx';
import Assistant from './Assistant.tsx';
import Settings from './Settings.tsx';

const FALLBACK_PORTS: Port[] = [
  { code: 'LAX', name: 'Port of Los Angeles', currency: 'USD', symbol: '$', language: 'en', customs_agency: 'CBP' },
  { code: 'SHA', name: 'Port of Shanghai (Yangshan)', currency: 'CNY', symbol: '¥', language: 'zh', customs_agency: '海关' },
  { code: 'RTM', name: 'Port of Rotterdam', currency: 'EUR', symbol: '€', language: 'en', customs_agency: 'Dutch Customs' },
];

export default function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null), [ports, setPorts] = useState(FALLBACK_PORTS);
  const [view, setView] = useState<'operations' | 'assistant'>('operations');
  const [jobs, setJobs] = useState<Job[]>([]), [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [generating, setGenerating] = useState(false), [decisionBusy, setDecisionBusy] = useState(false);
  const [error, setError] = useState(''), [expired, setExpired] = useState(false), [toast, setToast] = useState('');
  const [settings, setSettings] = useState(false), [evidence, setEvidence] = useState<string | null>(null);
  const [topN, setTopN] = useState(5), [useModel, setUseModel] = useState(false), [uncertain, setUncertain] = useState(false), [pollPaused, setPollPaused] = useState(false), [pollTick, setPollTick] = useState(0);
  const generateLock = useRef(false), scenarioLock = useRef(false), decisionLock = useRef(false), intent = useRef<RequestIntent | null>(null);
  const onError = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === -1) return;
    setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
    if (err instanceof ApiError && err.status === 401) { setExpired(true); setSettings(false); }
  }, []);
  const notify = useCallback((message: string) => setToast(message), []);
  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(''), 6500); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => {
    let active = true;
    loadSession().then(async data => {
      if (!active) return;
      setSnapshot(data); setLoading(false);
      try { const history = await api.plans(); if (active) { setJobs(previous => previous.length ? previous : history.plans); setSelectedId(previous => preferredPlanId(history.plans, previous)); } }
      catch (err) { if (active) onError(err); }
    }).catch(err => { if (active) { setLoading(false); onError(err); } });
    api.ports().then(data => { if (active) setPorts(data.ports); }).catch(() => { /* Public profile names remain usable; session errors surface separately. */ });
    return () => { active = false; };
  }, [onError]);
  useEffect(() => { if (!snapshot?.model.configured) setUseModel(false); }, [snapshot?.model.configured]);
  useEffect(() => {
    if (!snapshot?.model.key_expires_at || !snapshot.model.configured) return;
    const delay = new Date(snapshot.model.key_expires_at).getTime() - Date.now();
    const timer = window.setTimeout(() => { api.session().then(setSnapshot).catch(onError); }, Math.max(100, delay + 250));
    return () => clearTimeout(timer);
  }, [snapshot?.model.key_expires_at, snapshot?.model.configured, onError]);
  const selectedJob = jobs.find(job => job.id === selectedId) || null;
  useEffect(() => {
    if (!selectedJob || !jobIsRunning(selectedJob) || expired || pollPaused) return;
    let active = true;
    const timer = window.setTimeout(() => { api.plan(selectedJob.id).then(job => { if (active) setJobs(previous => mergeJob(previous, job)); }).catch(err => { if (active) { setPollPaused(true); onError(err); } }); }, 1200);
    return () => { active = false; clearTimeout(timer); };
  }, [selectedJob, expired, pollPaused, pollTick, onError]);

  async function refresh() {
    if (busy || decisionLock.current || generateLock.current) return;
    setBusy(true); setError('');
    try { setSnapshot(await api.session()); const history = await api.plans(); setJobs(history.plans); setSelectedId(previous => preferredPlanId(history.plans, previous)); notify('Queue and plan history refreshed. No model was called.'); }
    catch (err) { onError(err); } finally { setBusy(false); }
  }
  async function restart() {
    setLoading(true); setError('');
    try { setSnapshot(await newSession()); setJobs([]); setSelectedId(null); setExpired(false); setUncertain(false); intent.current = null; notify('New temporary session started. Connect Claude to authorize model requests.'); }
    catch (err) { onError(err); } finally { setLoading(false); }
  }
  async function patchScenario(patch: Partial<Scenario>) {
    if (!snapshot || scenarioLock.current || busy || generating) return;
    scenarioLock.current = true; setBusy(true); setError('');
    try { const next = await api.scenario(patch, snapshot.revision); setSnapshot(next); setUncertain(false); intent.current = null; notify('Conditions updated. Previous plans are retained and marked outdated.'); }
    catch (err) { onError(err); if (err instanceof ApiError && [409, 412].includes(err.status)) { try { setSnapshot(await api.session()); } catch (readErr) { onError(readErr); } } }
    finally { setBusy(false); scenarioLock.current = false; }
  }
  async function generate() {
    if (!snapshot || generateLock.current || jobs.some(jobIsRunning) || busy) return;
    generateLock.current = true; setGenerating(true); setError(''); setPollPaused(false);
    const current = requestIntent(intent.current, snapshot.revision, topN, useModel, () => crypto.randomUUID());
    intent.current = current;
    try { const job = await api.generate({ top_n: current.top_n, use_model: current.use_model }, current.revision, current.key); setJobs(previous => mergeJob(previous, job)); setSelectedId(job.id); intent.current = null; setUncertain(false); }
    catch (err) { onError(err); setUncertain(err instanceof ApiError && err.status === 0); if (err instanceof ApiError && [409, 412].includes(err.status)) { intent.current = null; try { setSnapshot(await api.session()); } catch (readErr) { onError(readErr); } } }
    finally { generateLock.current = false; setGenerating(false); }
  }
  async function decision(job: Job, action: PlanAction, choice: 'approved' | 'rejected', note: string) {
    if (!snapshot || decisionLock.current || busy) return;
    decisionLock.current = true; setDecisionBusy(true); setError('');
    try { const updated = await api.decide(job.id, { container_id: action.container_id, blocker: action.blocker, decision: choice, note }, snapshot.revision); setJobs(previous => mergeJob(previous, updated)); notify(choice === 'approved' ? 'Approved for human follow-up. Nothing was sent or released.' : 'Rejection recorded. No operational action was taken.'); }
    catch (err) { onError(err); if (err instanceof ApiError && [409, 412].includes(err.status)) { try { setSnapshot(await api.session()); } catch (readErr) { onError(readErr); } } }
    finally { decisionLock.current = false; setDecisionBusy(false); }
  }
  function modelUpdated(model: ModelStatus) {
    setSnapshot(previous => previous ? { ...previous, model } : previous);
    notify(model.configured ? model.source === 'render_environment' ? 'Team Claude connected for this session. No model call was made.' : 'Personal key saved temporarily. No model call was made.' : 'Claude disconnected for this session. The team key remains in Render; any personal key was forgotten.');
  }
  function changeView(next: 'operations' | 'assistant') { setView(next); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  const port = ports.find(item => item.code === snapshot?.scenario.port) || ports[0];
  const row = snapshot?.queue.find(item => item.container_id === evidence);
  const crisis = snapshot && (snapshot.scenario.lanes_open < 8 || !snapshot.scenario.customs_online || !snapshot.scenario.power_zone_b);
  return <div className="app-shell">
    <aside className="sidebar"><a href="/" className="brand" aria-label="Gate Triage home"><span className="brand-mark"><Layers3 size={24} /></span><span>Gate<span className="brand-light">Triage</span><small>TERMINAL OPERATIONS</small></span></a>
      <div className="workspace-label">WORKSPACE / PORT PROFILE</div><label className="port-switcher"><span className="workspace-avatar"><Anchor size={18} /></span><select aria-label="Port profile" value={snapshot?.scenario.port || 'LAX'} disabled={!snapshot || busy || generating || expired} onChange={event => patchScenario({ port: event.target.value as PortCode })}>{ports.map(item => <option key={item.code} value={item.code}>{item.code} · {item.name.replace('Port of ', '')}</option>)}</select></label>
      <nav aria-label="Main navigation"><button className={`nav-item ${view === 'operations' ? 'active' : ''}`} onClick={() => changeView('operations')}><LayoutDashboard size={18} />Operations{snapshot && <span className="nav-count">{snapshot.queue.length}</span>}</button><button className={`nav-item ${view === 'assistant' ? 'active' : ''}`} onClick={() => changeView('assistant')}><Sparkles size={18} />Action assistant{jobIsRunning(selectedJob) && <LoaderCircle className="spin" size={14} />}</button></nav>
      <div className="sidebar-note"><ShieldCheck size={18} /><div><strong>Human decisions. Clear evidence.</strong><p>Nothing is sent, released, or operationally changed by this assistant.</p></div></div>
      <div className="sidebar-bottom"><button className="nav-item" onClick={() => setSettings(true)} disabled={!snapshot || expired}><KeyRound size={17} /><span>Claude connection</span><span className={`status-dot ${snapshot?.model.configured ? '' : 'muted'}`} /></button><a className="nav-item" href="/docs" target="_blank" rel="noreferrer"><CircleHelp size={17} />API reference <ArrowRight size={13} /></a><div className="user-row"><span className="user-avatar">GP</span><div>Gate Planner<small>Isolated preview session</small></div><span className="status-dot" /></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={12} /><strong>{view === 'operations' ? 'Operations overview' : 'Action assistant'}</strong></div><div className="topbar-actions"><span className="connection"><span className={`status-dot ${expired ? 'offline' : ''}`} />{expired ? 'Session expired' : snapshot ? 'Backend connected' : 'Connecting'}</span><button className="icon-button" aria-label="Refresh queue and history" onClick={refresh} disabled={!snapshot || busy || decisionBusy || expired}><RefreshCw size={16} className={busy ? 'spin' : ''} /></button><button className="icon-button" aria-label="Open Claude settings" onClick={() => setSettings(true)} disabled={!snapshot || expired}><Settings2 size={17} /></button></div></header>
      <main><div className="page-heading"><div><div className="eyebrow"><span />OPERATIONS WORKSPACE</div><h1>{view === 'operations' ? 'Clarity at the gate.' : 'From a blocker to a next step.'}</h1><p>{view === 'operations' ? 'See the exceptions, understand the evidence, coordinate what happens next.' : 'Explicit requests. Grounded numbers. Reviewable human follow-up.'}</p></div><button className="button secondary" onClick={() => setSettings(true)} disabled={!snapshot || expired}><KeyRound size={15} />{snapshot?.model.configured ? 'Claude configured' : 'Connect Claude'}</button></div>
        {error && <div className="error-banner" role="alert"><ShieldCheck size={18} /><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={15} /></button></div>}
        {expired ? <div className="loading-workspace"><ShieldCheck size={38} /><h2>This temporary session has expired</h2><p>Start a fresh preview session to continue. Your previous key is not replayed or recovered by the browser.</p><button className="button primary" onClick={restart} disabled={loading}>{loading ? <LoaderCircle size={16} className="spin" /> : <RefreshCw size={16} />}Start a new session</button></div> : loading ? <div className="loading-workspace" role="status"><LoaderCircle size={36} className="spin" /><h2>Preparing your operations workspace</h2><p>Loading the synthetic container queue. No model is called.</p></div> : !snapshot ? <div className="loading-workspace"><Activity size={36} /><h2>Could not load the workspace</h2><p>The backend may be waking up. Try starting a new temporary session.</p><button className="button primary" onClick={restart}>Try again</button></div> : <>
          <div className="context-bar"><span className="simulation-label"><Globe2 size={13} />SYNTHETIC DATA</span><span className="context-divider" /><strong>{port.name}</strong><span>{port.currency} · {port.customs_agency}</span><span className="context-info">Same 100-container cohort · localized profile</span></div>
          <ScenarioBar scenario={snapshot.scenario} disabled={busy || generating || decisionBusy} crisis={!!crisis} onChange={patchScenario} />
          {view === 'operations' ? <Operations snapshot={snapshot} onInspect={item => setEvidence(item.container_id)} onAssistant={() => changeView('assistant')} /> : <Assistant snapshot={snapshot} jobs={jobs} selectedId={selectedId} topN={topN} useModel={useModel} generating={generating || busy} uncertain={uncertain} decisionBusy={decisionBusy || busy} onSelect={id => { setSelectedId(id); setPollPaused(false); }} onTopN={value => { setTopN(value); setUncertain(false); intent.current = null; }} onUseModel={value => { setUseModel(value); setUncertain(false); intent.current = null; }} onGenerate={generate} onDecision={decision} onInspect={item => setEvidence(item.container_id)} onSettings={() => setSettings(true)} onRetryPoll={() => { setPollPaused(false); setPollTick(value => value + 1); }} notify={notify} />}
          {pollPaused && jobIsRunning(selectedJob) && <div className="stale-banner"><span>Status polling paused after a connection issue. The server job may still be running.</span><button className="button secondary small" onClick={() => { setPollPaused(false); setPollTick(value => value + 1); }}>Resume status checks</button></div>}
          <footer className="app-footer"><span><span className="status-dot" />GATE TRIAGE · ADVISORY DEMO</span><span>Session until {dateTime(snapshot.expires_at)} · Temporary server memory</span></footer>
        </>}
      </main>
    </div>
    {settings && snapshot && !expired && <Settings model={snapshot.model} onClose={() => setSettings(false)} onUpdate={modelUpdated} onError={err => { if (err instanceof ApiError && err.status === 401) onError(err); }} />}
    {row && !settings && <EvidenceDrawer row={row} onClose={() => setEvidence(null)} onAssistant={() => { setEvidence(null); changeView('assistant'); }} />}
    {toast && <div className="toast" role="status"><Check size={16} /><span>{toast}</span><button aria-label="Dismiss notification" onClick={() => setToast('')}><X size={14} /></button></div>}
  </div>;
}

function ScenarioBar({ scenario, disabled, crisis, onChange }: { scenario: Scenario; disabled: boolean; crisis: boolean; onChange: (patch: Partial<Scenario>) => void }) {
  const [lanes, setLanes] = useState(scenario.lanes_open);
  useEffect(() => setLanes(scenario.lanes_open), [scenario.lanes_open]);
  return <section className="scenario-bar" aria-label="Synthetic scenario controls"><div className="scenario-label"><Settings2 size={17} /><div><strong>Current conditions</strong><span>Change inputs · no model call</span></div><Badge tone={crisis ? 'amber' : 'teal'}>{crisis ? 'Disrupted' : 'Normal'}</Badge></div><div className="lane-control"><label htmlFor="lane-count">Open lanes <strong>{lanes} / 8</strong></label><div><input id="lane-count" type="range" min="0" max="8" step="1" value={lanes} disabled={disabled} onChange={event => setLanes(Number(event.target.value))} /><button className="button secondary small" disabled={disabled || lanes === scenario.lanes_open} onClick={() => onChange({ lanes_open: lanes })}>Apply</button></div></div><label className="scenario-toggle"><input type="checkbox" checked={scenario.customs_online} disabled={disabled} onChange={event => onChange({ customs_online: event.target.checked })} /><span><strong>Customs connection</strong><small>{scenario.customs_online ? 'Online' : 'Offline · cannot verify new clearance'}</small></span></label><label className="scenario-toggle"><input type="checkbox" checked={scenario.power_zone_b} disabled={disabled} onChange={event => onChange({ power_zone_b: event.target.checked })} /><span><strong>Zone B power</strong><small>{scenario.power_zone_b ? 'Powered' : 'Offline · review reefer relocation'}</small></span></label><button className="text-button" disabled={disabled || !crisis} onClick={() => { setLanes(8); onChange({ lanes_open: 8, customs_online: true, power_zone_b: true }); }}><RefreshCw size={12} />Reset</button></section>;
}
