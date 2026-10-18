import { useYardLocale } from './YardLocale.tsx';
import { ArrowRight, Box, Check, CheckCheck, ClipboardCheck, Clock3, LogOut, Play, Search, ShieldCheck, TriangleAlert } from 'lucide-react';
import { useMemo, useState } from 'react';
import { YardModal as Modal } from './YardLocale.tsx';
import { carrierName, ISSUE, issuesFor, SCENARIOS } from './yard-demo.ts';
import type { DemoContainer, DemoScenario } from './yard-demo.ts';
import { releaseBlockers, VERIFICATION, WORK_STAGE } from './yard-workflow.ts';
import type { PostActionJob, WorkflowEvent, YardRun } from './yard-workflow.ts';
import './yard-post-actions.css';
type Props = {
    run: YardRun;
    catalog: DemoContainer[];
    scenario: DemoScenario;
    freeSlots: number;
    onEvent: (event: WorkflowEvent) => boolean;
    onSelect: (c: DemoContainer) => void;
    onInventory: (c: DemoContainer) => void;
    onGateOut: (c: DemoContainer) => void;
};
const stamp = () => new Date().toISOString();
const place = (c: {
    block: string;
    bay: number;
    row: number;
    tier: number;
}) => `${c.block} · bay ${String(c.bay).padStart(2, '0')} / row ${c.row} / tier ${c.tier}`;
export default function YardPostActions({ run, catalog, scenario, freeSlots, onEvent, onSelect, onInventory, onGateOut }: Props) {
    const { t, formatTime } = useYardLocale();
    const [tab, setTab] = useState<'active' | 'resolved' | 'departed'>('active'), [query, setQuery] = useState('');
    const [editor, setEditor] = useState<{
        key: string;
        mode: 'work' | 'verify';
    } | null>(null);
    const [text, setText] = useState(''), [confirmed, setConfirmed] = useState(false);
    const byId = useMemo(() => new Map(catalog.map(c => [c.id, c])), [catalog]);
    const departedIds = new Set(run.departures.map(d => d.containerId));
    const active = run.jobs.filter(j => j.stage !== 'resolved' && !departedIds.has(j.containerId));
    const resolved = run.jobs.filter(j => j.stage === 'resolved' && !departedIds.has(j.containerId));
    const q = query.trim().toLowerCase();
    const matches = (id: string) => { const c = byId.get(id); return c && `${c.id} ${c.block} ${c.carrier} ${carrierName(c.carrier)}`.toLowerCase().includes(q); };
    const jobs = (tab === 'active' ? active : resolved).filter(j => matches(j.containerId));
    const departures = run.departures.filter(d => matches(d.containerId));
    const job = editor ? run.jobs.find(j => j.key === editor.key) : undefined;
    function edit(j: PostActionJob, mode: 'work' | 'verify') { setText(''); setConfirmed(false); setEditor({ key: j.key, mode }); }
    function submit() {
        if (!editor || !job)
            return;
        const ok = onEvent(editor.mode === 'work' ? { type: 'complete_work', key: job.key, note: text, at: stamp() } : { type: 'verify', key: job.key, evidence: text, confirmed, at: stamp() });
        if (ok) {
            if (editor.mode === 'verify')
                setTab('resolved');
            setEditor(null);
        }
    }
    return <section className="yd-post-workspace" aria-label={t("Post-action queue")}>
    <div className="yd-post-summary"><Summary icon={<Clock3 size={19}/>} label={t("Active tasks")} value={active.length}/><Summary icon={<CheckCheck size={19}/>} label={t("Resolved tasks \u00B7 in yard")} value={resolved.length}/><Summary icon={<LogOut size={19}/>} label={t("Confirmed gate-outs")} value={run.departures.length}/><Summary icon={<Box size={19}/>} label={t("Free modeled tier slots")} value={freeSlots}/></div>
    <div className="yd-post-explainer"><ShieldCheck size={18}/><p><strong>{t("Acceptance starts the follow-through.")}</strong>{t(" Work completion needs result verification. A normal container remains in inventory; only confirmed physical gate-out releases its occupied tier slot. This is a locally saved simulation.")}</p></div>
    <div className="yd-post-toolbar"><div className="yd-post-tabs" role="tablist" aria-label={t("Post-action status")}><button role="tab" aria-selected={tab === 'active'} onClick={() => setTab('active')}>{t("Active ")}<b>{t(active.length)}</b></button><button role="tab" aria-selected={tab === 'resolved'} onClick={() => setTab('resolved')}>{t("Resolved ")}<b>{t(resolved.length)}</b></button><button role="tab" aria-selected={tab === 'departed'} onClick={() => setTab('departed')}>{t("Gated out ")}<b>{t(run.departures.length)}</b></button></div><label className="yd-search"><Search size={15}/><input aria-label={t("Search post-action queue")} placeholder={t("Container, carrier or block\u2026")} value={query} onChange={e => setQuery(e.target.value)}/></label></div>
    <div className="yd-post-list">{t(tab !== 'departed' ? jobs.map(j => {
            const c = byId.get(j.containerId)!;
            const remaining = issuesFor(c, scenario), blockers = releaseBlockers(c, run, scenario);
            return <article className={`yd-post-card yd-post-${j.stage}`} key={j.key}>
        <header><button className="yd-post-container" onClick={() => onSelect(c)}><Box size={19}/><span><strong>{t(c.id)}</strong><small>{t(carrierName(c.carrier))}{t(" \u00B7 ")}{t(place(c))}</small></span></button><span className={`yd-work-stage ${j.stage}`}>{t(j.stage === 'resolved' ? <Check size={14}/> : <Clock3 size={14}/>)}{t(WORK_STAGE[j.stage].label)}</span></header>
        <div className="yd-post-task"><h3>{t(ISSUE[j.issue].action)}</h3><p>{t(ISSUE[j.issue].owner)} <span>{t("\u00B7 accepted in ")}{t(SCENARIOS[j.scenario].name)}</span></p></div>
        <ol className="yd-work-timeline">{t((['queued', 'in_progress', 'awaiting_verification', 'resolved'] as const).map((s, i, stages) => <li key={s} className={stages.indexOf(j.stage) >= i ? 'reached' : ''}><i>{t(stages.indexOf(j.stage) > i ? <Check size={11}/> : i + 1)}</i><span>{t(WORK_STAGE[s].label)}</span></li>))}</ol>
        {t(j.note && <p className="yd-post-note"><b>{t("Handoff")}</b>{j.note}</p>)}{t(j.workNote && <p className="yd-post-note"><b>{t("Work reported")}</b>{j.workNote}</p>)}{t(j.evidence && <p className="yd-post-note verified"><b>{t("Verified evidence")}</b>{j.evidence}</p>)}
        {t(j.stage === 'resolved' && <div className={`yd-post-outcome ${remaining.length ? 'blocked' : ''}`}>{t(remaining.length ? <TriangleAlert size={17}/> : <CheckCheck size={17}/>)}<div><strong>{t(remaining.length ? `${remaining.length} independent exception${remaining.length === 1 ? '' : 's'} still active` : 'Normal · back in inventory')}</strong><p>{t(remaining.length ? remaining.map(i => ISSUE[i].label).join(' · ') : 'The container still occupies its slot. Resolving a task does not imply departure.')}</p></div></div>)}
        <footer><span>{t("Updated ")}{t(formatTime(j.updatedAt))}</span><div>{t(j.stage === 'queued' && <button className="yd-primary" onClick={() => onEvent({ type: 'start', key: j.key, at: stamp() })}><Play size={14}/>{t("Start work")}</button>)}{t(j.stage === 'in_progress' && <button className="yd-primary" onClick={() => edit(j, 'work')}><ClipboardCheck size={14}/>{t("Report work completed")}</button>)}{t(j.stage === 'awaiting_verification' && <button className="yd-primary" onClick={() => edit(j, 'verify')}><ShieldCheck size={14}/>{t("Verify & resolve")}</button>)}{t(j.stage === 'resolved' && <><button className="yd-secondary" onClick={() => onInventory(c)}>{t("View in inventory ")}<ArrowRight size={13}/></button><button className="yd-primary" disabled={blockers.length > 0} title={t(blockers.length ? blockers.join('; ') : 'Confirm permission and actual gate-out')} onClick={() => onGateOut(c)}><LogOut size={14}/>{t("Release & gate-out")}</button></>)}</div></footer>
        <details className="yd-work-audit"><summary>{t("Task history \u00B7 ")}{t(j.events.length)}{t(" events")}</summary>{t(j.events.map((e, i) => <p key={`${e.at}-${i}`}><b>{t(WORK_STAGE[e.stage].label)}</b><span>{t(formatTime(e.at))}</span><small>{e.note}</small></p>))}</details>
      </article>;
        }) : departures.map(d => { const c = byId.get(d.containerId)!; return <article key={d.containerId} className="yd-post-card yd-post-departed"><header><button className="yd-post-container" onClick={() => onSelect(c)}><LogOut size={20}/><span><strong>{t(c.id)}</strong><small>{t(carrierName(c.carrier))}{t(" \u00B7 last location ")}{t(place(d))}</small></span></button><span className="yd-work-stage departed">{t("Gated out")}</span></header><div className="yd-post-outcome"><CheckCheck size={19}/><div><strong>{t("Removed from current inventory \u00B7 1 modeled tier slot freed")}</strong><p>{t(d.plugId ? `Reefer connection ${d.plugId} is no longer occupied. Circuit state is evaluated separately.` : 'Remaining stack positions are retained; a ground cell becomes empty when its last container leaves.')}</p></div></div><p className="yd-post-note verified"><b>{t("Gate-out evidence")}</b>{d.evidence}</p><footer><span>{t("Confirmed ")}{t(formatTime(d.at))}</span><span className="yd-post-archived">{t("Retained in audit \u00B7 excluded from yard queries")}</span></footer></article>; }))}
    {t((tab === 'departed' ? !departures.length : !jobs.length) && <div className="yd-empty"><ClipboardCheck size={31}/><h3>{t(q ? 'No matching records' : tab === 'active' ? 'No active post-action tasks' : tab === 'resolved' ? 'No verified resolutions yet' : 'No confirmed gate-outs yet')}</h3><p>{t(tab === 'active' ? 'Accept a suggestion in Actions or the container detail to start its follow-through.' : tab === 'resolved' ? 'Complete work and verify the result to move a task here.' : 'Release permission and physical exit must both be confirmed.')}</p></div>)}</div>
    {t(editor && job && <Modal title={t(editor.mode === 'work' ? 'Report work completed' : 'Verify result & resolve')} subtitle={t(`${job.containerId} · ${ISSUE[job.issue].short}`)} onClose={() => setEditor(null)}><div className="yd-work-editor"><p>{t(editor.mode === 'work' ? 'Describe the completed work. The exception stays active until the result is verified.' : VERIFICATION[job.issue])}</p><label htmlFor="yd-work-evidence">{t(editor.mode === 'work' ? 'Work summary' : 'Evidence reference / verification note')}</label><textarea id="yd-work-evidence" rows={3} maxLength={1000} value={text} onChange={e => setText(e.target.value)} placeholder={t(editor.mode === 'work' ? 'What was done, and by whom?' : 'For demo use, enter a clearly labeled simulated verification reference.')}/>{t(editor.mode === 'verify' && <label className="yd-work-confirm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/><span>{t("I have verified the stated result for this container in the demo.")}</span></label>)}<p className="yd-work-small">{t("This updates simulated state only. Independent exceptions remain active; no equipment or external authority is controlled.")}</p><div className="yd-work-editor-actions"><button className="yd-secondary" onClick={() => setEditor(null)}>{t("Cancel")}</button><button className="yd-primary" disabled={text.trim().length < 3 || editor.mode === 'verify' && !confirmed} onClick={submit}>{t(editor.mode === 'work' ? 'Send for verification' : 'Confirm resolved')}</button></div></div></Modal>)}
  </section>;
}
function Summary({ icon, label, value }: {
    icon: React.ReactNode;
    label: string;
    value: number;
}) { const { t, number } = useYardLocale(); return <div><span>{t(icon)}{t(label)}</span><strong>{t(number(value))}</strong></div>; }
export function GateOutModal({ container, blockers, onConfirm, onClose }: {
    container: DemoContainer;
    blockers: string[];
    onConfirm: (evidence: string, clearance: boolean, exited: boolean) => boolean;
    onClose: () => void;
}) {
    const { t } = useYardLocale();
    const [evidence, setEvidence] = useState(''), [clearance, setClearance] = useState(false), [exited, setExited] = useState(false);
    return <Modal title={t("Confirm release & physical gate-out")} subtitle={t(`${container.id} · ${place(container)}`)} onClose={onClose}><div className="yd-work-editor"><p>{t("Release clearance alone leaves the container in inventory. Confirm its physical exit to remove it from the yard and free one modeled tier slot.")}</p>{t(blockers.length > 0 && <div className="yd-gate-blockers"><strong>{t("Gate-out is blocked")}</strong><ul>{t(blockers.map((b, i) => <li key={`${b}-${i}`}>{t(b)}</li>))}</ul></div>)}<label className="yd-work-confirm"><input type="checkbox" checked={clearance} onChange={e => setClearance(e.target.checked)}/><span>{t("Required carrier/customs permissions and pickup conditions are confirmed for this demo.")}</span></label><label className="yd-work-confirm"><input type="checkbox" checked={exited} onChange={e => setExited(e.target.checked)}/><span>{t("The container has physically gated out in the simulation.")}</span></label><label htmlFor="yd-gate-evidence">{t("Gate-out reference / confirmation note")}</label><textarea id="yd-gate-evidence" rows={3} maxLength={1000} value={evidence} onChange={e => setEvidence(e.target.value)} placeholder={t("e.g. SIMULATED gate-out ticket and operator confirmation")}/><p className="yd-work-small">{t("The record is removed from active stock and queries. Its last position and evidence remain in the Gated out audit tab.")}</p><div className="yd-work-editor-actions"><button className="yd-secondary" onClick={onClose}>{t("Cancel")}</button><button className="yd-primary" disabled={blockers.length > 0 || !clearance || !exited || evidence.trim().length < 3} onClick={() => { if (onConfirm(evidence, clearance, exited))
        onClose(); }}><LogOut size={15}/>{t("Confirm gate-out")}</button></div></div></Modal>;
}
