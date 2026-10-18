import { useYardBackend } from './useYardBackend.ts';
import { useYardLocale, YardLocaleProvider } from './YardLocale.tsx';
import { Anchor, ArrowDownToLine, ArrowLeft, ArrowRight, Box, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, ClipboardCheck, Filter, History, Layers3, LayoutGrid, ListFilter, LogOut, Map as MapIcon, Maximize2, Minus, Plus, RotateCcw, Search, ShieldCheck, Snowflake, Sparkles, TriangleAlert, X, Zap } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { YardModal as Modal } from './YardLocale.tsx';
import { actionFor, actionsFor, carrierName, CARGO_COLOR, circuitOffline, compareActions, compareAttention, congestionExposure, exceptionColor, isPerishable, issuePresentation, PERISHABLE_COLOR, priorityChange, ISSUE, issuesFor, makeDemo, plugSummary, primaryIssue, PORTS, QUADRANTS, queryYardInventory, SCENARIOS, selectContainers, summarize, supplyFor } from './yard-demo.ts';
import type { DemoAction, DemoBlock, DemoContainer, DemoDecision, DemoPort, DemoScenario, Issue, Quadrant, YardLookup } from './yard-demo.ts';
import YardStackTiers from './YardStackTiers.tsx';
import YardInventoryQuery from './YardInventoryQuery.tsx';
import YardPostActions, { GateOutModal } from './YardPostActions.tsx';
import YardAssistant from './YardAssistant.tsx';
import YardEvidence from './YardEvidence.tsx';
import './yard-priority.css';
import { releaseBlockers, WORK_STAGE } from './yard-workflow.ts';
import type { WorkflowEvent } from './yard-workflow.ts';
import './yard-prototype.css';
import './yard-query-focus.css';
const location = (c: DemoContainer) => `${c.block} · ${String(c.bay).padStart(2, '0')} / ${c.row} / ${c.tier}`;
const cargoLabel = { dry: 'Dry cargo', reefer: 'Refrigerated', hazmat: 'Hazardous cargo', empty: 'Empty equipment' };
export default function YardPrototype() {
    const [port, setPort] = useState<DemoPort>('la');
    return <YardLocaleProvider port={port}><YardWorkspace key={port} port={port} onPortChange={setPort}/></YardLocaleProvider>;
}
function YardWorkspace(props: { port: DemoPort; onPortChange: (port: DemoPort) => void }) {
    const backend = useYardBackend(props.port);
    const { t } = useYardLocale();
    if (!backend.snapshot) return <div className="yd-backend-loading" role="status"><Layers3 size={32} /><h1>Gate Triage</h1><p>{t(backend.error || 'Connecting to the yard database…')}</p>{backend.error && <button className="yd-primary" onClick={() => void backend.refresh()}>{t('Retry connection')}</button>}</div>;
    return <YardLoadedWorkspace {...props} backend={backend} />;
}
function YardLoadedWorkspace({ port, onPortChange, backend }: { port: DemoPort; onPortChange: (port: DemoPort) => void; backend: ReturnType<typeof useYardBackend> }) {
    const { t, number, formatTime } = useYardLocale();
    const { run, blocks, catalog, scenario } = backend.snapshot!;
    const saving = backend.busy || backend.uncertain || !backend.connected;
    const seed = run.seed, decisions = run.decisions;
    const [gateTarget, setGateTarget] = useState<string | null>(null);
    const [view, setView] = useState<'yard' | 'queue' | 'post' | 'history'>('yard'), [selectedId, setSelectedId] = useState(''), [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
    const [query, setQuery] = useState(''), [block, setBlock] = useState('all'), [exceptionsOnly, setExceptionsOnly] = useState(true), [mapOpen, setMapOpen] = useState(true);
    const [layer, setLayer] = useState<'exceptions' | 'cargo' | 'power'>('exceptions'), [zoom, setZoom] = useState(1), [page, setPage] = useState(0), [quadrant, setQuadrant] = useState<Quadrant | null>(null);
    const [note, setNote] = useState(''), [toast, setToast] = useState(''), [guide, setGuide] = useState(false);
    const [focus, setFocus] = useState<string | null>(null), [queryOpen, setQueryOpen] = useState(() => window.innerWidth > 1100);
    const [mapSelectionVisible, setMapSelectionVisible] = useState(false);
    const [stackChoice, setStackChoice] = useState<{ blockId: string; bay: number; row: number } | null>(null);
    const [lookup, setLookup] = useState<YardLookup>({ containerId: '', company: '' }), [lookupActive, setLookupActive] = useState(false);
    const queueResults = useRef<HTMLElement>(null);
    const scrollToFilteredQueue = useRef(false);
    const restoreViewport = useRef<{
        page: number;
        scroll: number;
    } | null>(null);
    const returnState = useRef<{
        view: 'yard' | 'queue' | 'post' | 'history';
        queryOpen: boolean;
        block: string;
        query: string;
        exceptionsOnly: boolean;
        quadrant: Quadrant | null;
        page: number;
        zoom: number;
        mapOpen: boolean;
        lookupActive: boolean;
        selectedId: string;
        selectedIssue: Issue | null;
        scroll: number;
    } | null>(null);
    const all = useMemo(() => blocks.flatMap(b => b.containers), [blocks]);
    const focusedBlock = focus && focus !== 'yard' ? blocks.find(b => b.id === focus) : undefined;
    const lookupMatches = useMemo(() => queryYardInventory(all, lookup), [all, lookup]);
    const stats = useMemo(() => summarize(blocks, scenario), [blocks, scenario]);
    const scopeRows = useMemo(() => selectContainers(lookupActive ? lookupMatches : all, scenario, query, focusedBlock?.id || block, exceptionsOnly), [all, lookupActive, lookupMatches, scenario, query, focusedBlock, block, exceptionsOnly]);
    const pending = useMemo(() => scopeRows.flatMap(c => actionsFor(c, scenario)).filter(a => !run.jobs.some(j => j.containerId === a.container.id && j.issue === a.issue && j.stage !== 'resolved') && !decisions.some(d => d.id === a.container.id && d.issue === a.issue && d.scenario === scenario && (d.observationVersion || 0) === (a.container.observationVersion || 0))).sort(compareActions), [scopeRows, scenario, decisions, run.jobs]);
    const entries = useMemo(() => view === 'queue' ? pending.filter(a => !quadrant || a.quadrant === quadrant).map(a => ({ container: a.container, issue: a.issue as Issue })) : scopeRows.map(c => ({ container: c, issue: primaryIssue(c, scenario) })), [scopeRows, pending, quadrant, view, scenario]);
    const rows = entries.map(e => e.container);
    const first = useMemo(() => [...all].sort((a, b) => compareAttention(a, b, scenario))[0], [all, scenario]);
    const selected = catalog.find(c => c.id === selectedId) || first || catalog[0], departed = selected.yardStatus === 'departed';
    const selectedIssues = departed ? [] : issuesFor(selected, scenario);
    const issue = selectedIssue && selectedIssues.includes(selectedIssue) ? selectedIssue : departed ? 'clear' : primaryIssue(selected, scenario), meta = issuePresentation(selected, issue);
    const selectedAction = issue === 'clear' ? null : actionFor(selected, issue, scenario);
    const routineAction = actionsFor(selected, 'routine').find(a => a.issue === issue);
    const selectedExposure = congestionExposure(selected, scenario);
    const selectedBlock = blocks.find(b => b.id === selected.block)!;
    const decision = decisions.find(d => d.id === selected.id && d.scenario === scenario && d.issue === issue && (d.observationVersion || 0) === (selected.observationVersion || 0));
    const selectedJob = run.jobs.find(j => j.containerId === selected.id && j.issue === issue && j.stage !== 'resolved');
    const activeJobs = run.jobs.filter(j => j.stage !== 'resolved').length;
    const blockers = departed ? [] : releaseBlockers(selected, run, scenario);
    const gateContainer = gateTarget ? catalog.find(c => c.id === gateTarget) : undefined;
    useEffect(() => { if (gateContainer?.yardStatus === 'departed') setGateTarget(null); }, [gateContainer]);
    const pages = Math.max(1, Math.ceil(rows.length / 8)), currentPage = Math.min(page, pages - 1);
    useEffect(() => { document.documentElement.lang = port === 'rotterdam' ? 'nl' : 'en'; document.title = `${PORTS[port].name} — Gate Triage${focusedBlock ? ` · ${t('Block')} ${focusedBlock.id}` : ''}`; return () => { document.documentElement.lang = 'en'; }; }, [focusedBlock, port, t]);
    useEffect(() => { const restore = restoreViewport.current; if (restore) {
        restoreViewport.current = null;
        setPage(restore.page);
        window.requestAnimationFrame(() => window.scrollTo({ top: restore.scroll, behavior: 'auto' }));
    }
    else
        setPage(0); }, [query, block, exceptionsOnly, scenario, quadrant, lookup, lookupActive, focus]);
    useEffect(() => {
        if (!scrollToFilteredQueue.current) return;
        scrollToFilteredQueue.current = false;
        const frame = window.requestAnimationFrame(() => {
            queueResults.current?.scrollIntoView({
                block: 'start',
                behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
            });
        });
        return () => window.cancelAnimationFrame(frame);
    }, [quadrant]);
    useEffect(() => { setNote(''); }, [selected.id, issue, scenario]);
    useEffect(() => { if (!toast)
        return; const t = window.setTimeout(() => setToast(''), 4500); return () => clearTimeout(t); }, [toast]);
    useEffect(() => { if (!focus || guide || gateTarget || stackChoice || view === 'post')
        return; function onKey(e: KeyboardEvent) { if (e.key === 'Escape')
        leaveFocus(); } window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey); }, [focus, guide, gateTarget, stackChoice, view]);
    async function chooseScenario(next: DemoScenario) { if (await backend.mutate({type:'scenario',scenario:next})) { setBlock(focusedBlock?.id || 'all'); setQuery(''); setQuadrant(null); setPage(0); } }
    async function reset() { if (!(await backend.mutate({type:'reset'}))) return; setGateTarget(null); setStackChoice(null); setSelectedId(''); setSelectedIssue(null); setQuadrant(null); setNote(''); setBlock('all'); setQuery(''); setPage(0); setFocus(null); returnState.current = null; setLookup({ containerId: '', company: '' }); setLookupActive(false); setToast('New server demo run created. Previous run retained in audit history.'); }
    function rememberOverview() { if (!focus)
        returnState.current = { view, queryOpen, block, query, exceptionsOnly, quadrant, page, zoom, mapOpen, lookupActive, selectedId, selectedIssue, scroll: window.scrollY }; }
    function openFocus(id: string, container?: DemoContainer) {
        const zone = blocks.find(b => b.id === id);
        if (id !== 'yard' && !zone || focus === id && !container)
            return;
        rememberOverview();
        setFocus(id);
        if (id !== 'yard') setQueryOpen(false);
        setMapSelectionVisible(false);
        setView('yard');
        setBlock(zone?.id || 'all');
        setQuery('');
        setExceptionsOnly(false);
        setLookupActive(false);
        setQuadrant(null);
        setPage(0);
        setZoom(1);
        setMapOpen(true);
        const c = container || (zone ? [...zone.containers].sort((a, b) => compareAttention(a, b, scenario))[0] : null);
        if (c) {
            setSelectedId(c.id);
            setSelectedIssue(null);
        }
        window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'auto' }));
    }
    function leaveFocus() {
        const previous = returnState.current;
        if (previous)
            restoreViewport.current = { page: previous.page, scroll: previous.scroll };
        setFocus(null);
        returnState.current = null;
        if (!previous) {
            setBlock('all');
            return;
        }
        setView(previous.view);
        setQueryOpen(previous.queryOpen);
        setBlock(previous.block);
        setQuery(previous.query);
        setExceptionsOnly(previous.exceptionsOnly);
        setQuadrant(previous.quadrant);
        setPage(previous.page);
        setZoom(previous.zoom);
        setMapOpen(previous.mapOpen);
        setLookupActive(previous.lookupActive);
        setSelectedId(previous.selectedId);
        setSelectedIssue(previous.selectedIssue);
    }
    function navigate(next: 'yard' | 'queue' | 'post' | 'history') { if (focus)
        leaveFocus(); setView(next); }
    function filterQuadrant(next: Quadrant) {
        scrollToFilteredQueue.current = true;
        setPage(0);
        setQuadrant(current => current === next ? null : next);
    }
    function showLookupInventory() { setFocus(null); returnState.current = null; setView('yard'); setLookupActive(true); setExceptionsOnly(false); setBlock('all'); setQuery(''); setQuadrant(null); setPage(0); if (lookupMatches[0]) {
        setSelectedId(lookupMatches[0].id);
        setSelectedIssue(null);
    } if (window.innerWidth <= 1100)
        setQueryOpen(false); }
    function selectInPlace(c: DemoContainer) { setSelectedId(c.id); setSelectedIssue(null); setMapSelectionVisible(true); if (!focus)
        document.getElementById('yd-inspector')?.scrollTo({ top: 0, behavior: 'auto' }); }
    function locate(c: DemoContainer) { selectInPlace(c); if (window.innerWidth <= 1100)
        setQueryOpen(false); }
    async function dispatchWorkflow(event: WorkflowEvent): Promise<boolean> {
        const { at: _clientTime, ...command } = event;
        const ok = await backend.mutate(command);
        if (ok) setToast(event.type === 'gate_out' ? 'Gate-out confirmed. Current inventory and the empty slot are updated.' : event.type === 'verify' ? 'Result verified. Independent exceptions remain active; normal stock stays in inventory.' : event.type === 'review' ? event.choice === 'accepted' ? 'Added to Post-action. The exception stays active until verification.' : 'Suggestion dismissed. Inventory is unchanged.' : 'Post-action task updated.');
        return ok;
    }
    function review(choice: DemoDecision['choice']) {
        if (decision || selectedJob || issue === 'clear' || departed)
            return;
        dispatchWorkflow({ type: 'review', containerId: selected.id, scenario, issue, choice, note: note.trim(), at: new Date().toISOString() });
    }
    function showInInventory(c: DemoContainer) {
        setFocus(null);
        returnState.current = null;
        setView('yard');
        setLookupActive(false);
        setExceptionsOnly(false);
        setBlock('all');
        setQuery(c.id);
        setQuadrant(null);
        setPage(0);
        selectInPlace(c);
        window.requestAnimationFrame(() => document.querySelector('.yd-queue')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    }
    function exportView() {
        const csv = [['Container', 'Block', 'Bay', 'Row', 'Tier', 'Cargo', 'Carrier', 'Carrier name', 'Yard status', 'Exception', 'Suggested action', 'Quadrant'], ...entries.map(({ container: c, issue: key }) => [c.id, c.block, String(c.bay), String(c.row), String(c.tier), c.cargo, c.carrier, carrierName(c.carrier), t(c.yardStatus), t(ISSUE[key].label), t(ISSUE[key].action), key === 'clear' ? '' : t(QUADRANTS[actionFor(c, key, scenario).quadrant].name)])].map(row => row.map(s => `"${t(s).replaceAll('"', '""')}"`).join(',')).join('\n');
        const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })), link = document.createElement('a');
        link.href = url;
        link.download = `yard-demo-${port}.csv`;
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        setToast(`Exported ${number(rows.length)} synthetic ${view === "queue" ? "actions" : "records"} from this view.`);
    }
    function select(c: DemoContainer, nextIssue: Issue | null = null) { setSelectedId(c.id); setSelectedIssue(nextIssue); if (window.innerWidth < 1000)
        document.getElementById('yd-inspector')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    return <div className={`yd-app yd-port-${port} ${queryOpen ? "yd-with-query" : ""} ${focus === "yard" ? "yd-focused" : focusedBlock ? "yd-block-focus" : ""} ${focus === "yard" && !mapSelectionVisible ? "yd-map-only" : ""}`}>
    <header className="yd-topbar"><a className="yd-brand" href="?preview=yard"><span><Layers3 size={23}/></span><strong>{t("Gate")}<span>{t("Triage")}</span><small>{t("YARD DECISION SUPPORT")}</small></strong></a><div className="yd-terminal"><Anchor size={16}/><label className="yd-port-picker"><span className="yd-sr-only">{t("Demo port")}</span><select aria-label={t("Demo port")} value={port} onChange={e => { onPortChange(e.target.value as DemoPort); window.scrollTo({ top: 0 }); }}><option value="la">{t("Los Angeles \u00B7 EN")}</option><option value="rotterdam">{t("Rotterdam \u00B7 NL")}</option></select><ChevronDown size={12}/></label><span className="yd-port-context"><b>{t("Demo terminal")}</b></span><span className="yd-demo-pill">{t("DEMO ONLY")}</span></div><div className="yd-top-actions"><span className={`yd-local ${backend.connected ? "" : "yd-storage-warning"}`}><i />{t(backend.busy ? "Saving to database…" : backend.connected ? "Connected · SQLite" : "Connection interrupted")}</span><button title={t("About this prototype")} aria-label={t("About this prototype")} onClick={() => setGuide(true)}><CircleHelp size={18}/></button><span className="yd-avatar">{t("GP")}</span></div></header>
    <aside className="yd-rail" aria-label={t("Workspace navigation")}><button title={t("Inventory query")} aria-label={t("Inventory query")} aria-expanded={queryOpen} className={queryOpen ? "selected" : ""} onClick={() => setQueryOpen(v => !v)}><Search size={21}/><span>{t("Query")}</span></button><button title={t("Yard overview")} aria-label={t("Yard overview")} className={view === 'yard' ? 'selected' : ''} onClick={() => navigate('yard')}><LayoutGrid size={21}/><span>{t("Yard")}</span></button><button title={t("Decision queue")} aria-label={t("Decision queue")} className={view === 'queue' ? 'selected' : ''} onClick={() => navigate('queue')}><ClipboardCheck size={21}/><span>{t("Actions")}</span></button><button title={t("Post-action queue")} aria-label={t("Post-action queue")} className={view === 'post' ? 'selected' : ''} onClick={() => navigate('post')}><CheckCheck size={21}/><span>{t("Post-action")}</span>{t(activeJobs > 0 && <i>{t(activeJobs)}</i>)}</button><button title={t("Review history")} aria-label={t("Review history")} className={view === 'history' ? 'selected' : ''} onClick={() => navigate('history')}><History size={21}/><span>{t("History")}</span>{t(decisions.length > 0 && <i>{t(decisions.length)}</i>)}</button><div className="yd-rail-bottom"><ShieldCheck size={22}/><span>{t("Human")}<br />{t("in control")}</span></div></aside>
    {t(queryOpen && <><button className="yd-query-backdrop" aria-label={t("Close inventory query overlay")} onClick={() => setQueryOpen(false)}/><YardInventoryQuery lookup={lookup} results={lookupMatches} total={all.length} scenario={scenario} selectedId={selected.id} onChange={setLookup} onSelect={locate} onShowAll={showLookupInventory} onClose={() => setQueryOpen(false)}/></>)}
    <main className="yd-main">{t(focus && <div className="yd-focus-navigation"><button onClick={leaveFocus} aria-label={t("Back to previous view")}><ArrowLeft size={21}/><span>{t("Back")}</span></button><span>{t("Yard overview ")}<ChevronRight size={15}/>{t(focusedBlock ? `Block ${focusedBlock.id}` : 'Expanded view')}</span><small>{t("ESC TO RETURN")}</small></div>)}<div className="yd-page-heading"><div><span className="yd-eyebrow">{t("OPERATIONS / ")}{t(view === 'history' ? 'REVIEW LOG' : 'YARD COORDINATION')}</span><h1>{t(focusedBlock ? `Block ${focusedBlock.id}` : focus === 'yard' ? 'Yard overview' : view === 'post' ? 'Every action. Followed through.' : view === 'history' ? 'A record of your decisions.' : view === 'queue' ? 'The right action. At the right time.' : 'Your yard. A clearer next move.')}</h1><p>{t(focusedBlock ? `${focusedBlock.purpose} · ${focusedBlock.flow}` : focus === 'yard' ? 'A larger spatial reference. Select a block to inspect its stacks and inventory.' : view === 'post' ? 'Track work, verify the result, and keep inventory in step with physical gate-out.' : view === 'history' ? 'Database-backed review decisions. Detailed task progress is in Post-action.' : view === 'queue' ? 'Importance × urgency. Reassessed against the current scenario, one action at a time.' : 'Different zones. Finite infrastructure. Evidence before action.')}</p></div><div className="yd-scenario"><label htmlFor="yd-scenario">{t("DEMO SCENARIO")}</label><div><Zap size={15}/><select id="yd-scenario" value={scenario} disabled={saving} onChange={e => chooseScenario(e.target.value as DemoScenario)}>{t(Object.entries(SCENARIOS).map(([key, value]) => <option key={key} value={key}>{t(value.name)}</option>))}</select><ChevronDown size={13}/></div></div></div>
      {backend.error && <div className="yd-backend-error" role="alert"><TriangleAlert size={17} /><span>{t(backend.error)}</span><button disabled={backend.busy} onClick={() => void (backend.uncertain ? backend.retry() : backend.refresh())}>{t(backend.uncertain ? 'Retry save' : 'Refresh data')}</button></div>}
      {t(!focus && view !== 'post' && <section className="yd-kpis" aria-label={t("Synthetic yard metrics")}><Metric label={t("Containers in yard")} value={number(stats.containers)} detail={t(`${blocks.length} synthetic blocks`)} icon={<Box size={18}/>}/><Metric label={t("Slot utilization")} value={`${Math.round(stats.containers / stats.capacity * 100)}%`} detail={t(`${number(stats.containers)} / ${number(stats.capacity)} modeled slots`)} icon={<Layers3 size={18}/>}/><Metric label={t("Flagged containers")} value={number(stats.exceptions)} detail={t(`${stats.urgent} high-priority containers`)} icon={<TriangleAlert size={18}/>} accent/><Metric label={t("Free modeled tier slots")} value={number(stats.capacity - stats.containers)} detail={t(`${run.departures.length} confirmed gate-outs · fixed capacity`)} icon={<Layers3 size={18}/>}/></section>)}{t(focusedBlock && <ZoneMetrics block={focusedBlock} scenario={scenario}/>)}
      {t(scenario !== 'routine' && <div className="yd-disruption"><span className="yd-live-dot"/><Zap size={17}/><div><strong>{t(SCENARIOS[scenario].name)}</strong><span>{t(SCENARIOS[scenario].detail)}{t(". Existing clearance restrictions remain visible.")}</span></div><button onClick={() => chooseScenario('routine')}>{t("Reset scenario ")}<RotateCcw size={13}/></button></div>)}
      {t(view === 'post' ? <YardPostActions run={run} catalog={catalog} scenario={scenario} busy={saving} error={backend.error} uncertain={backend.uncertain} onRetry={backend.retry} freeSlots={stats.capacity - stats.containers} onEvent={dispatchWorkflow} onSelect={selectInPlace} onInventory={showInInventory} onGateOut={c => setGateTarget(c.id)}/> : view !== 'history' ? <>
        {t(view === 'queue' && <ActionMatrix actions={pending} scenario={scenario} selected={quadrant} onFilter={filterQuadrant} onSelect={a => select(a.container, a.issue)}/>)}
        {t(view === 'yard' && <section className="yd-map-panel"><div className="yd-panel-title"><div><MapIcon size={17}/><h2>{t(focusedBlock ? `${focusedBlock.id} · stack layout` : "Yard overview")}</h2><span className="yd-muted-tag">{t(focusedBlock ? "BLOCK DETAIL" : "REFERENCE VIEW")}</span></div><div className="yd-map-title-actions">{t(!focus && <button className="yd-text-button" aria-label={t("Expand yard section")} onClick={() => openFocus("yard")}><Maximize2 size={15}/>{t("Expand")}</button>)}<button className="yd-text-button" onClick={() => setMapOpen(!mapOpen)}>{t(mapOpen ? 'Hide yard view' : 'Show yard view')} <Layers3 size={14}/></button></div></div>
          {t(mapOpen && <><div className="yd-map-controls"><div className="yd-layer-switch" aria-label={t("Map color layer")}><button aria-pressed={layer === 'exceptions'} className={layer === 'exceptions' ? 'selected' : ''} onClick={() => setLayer('exceptions')}><TriangleAlert size={13}/>{t("Exceptions")}</button><button aria-pressed={layer === 'cargo'} className={layer === 'cargo' ? 'selected' : ''} onClick={() => setLayer('cargo')}><Box size={13}/>{t("Cargo type")}</button><button aria-pressed={layer === 'power'} className={layer === 'power' ? 'selected' : ''} onClick={() => setLayer('power')}><Zap size={13}/>{t("Power infrastructure")}</button></div>{t(focusedBlock && <span className="yd-map-hint">{t("Select a stack to inspect its tiers")}</span>)}<div className="yd-zoom"><button aria-label={t("Zoom out")} disabled={zoom <= .7} onClick={() => setZoom(z => Math.max(.7, z - .25))}><Minus size={14}/></button><button aria-label={t("Reset map zoom")} onClick={() => setZoom(1)}>{t(Math.round(zoom * 100))}{t("%")}</button><button aria-label={t("Zoom in")} disabled={zoom >= 2.25} onClick={() => setZoom(z => Math.min(2.25, z + .25))}><Plus size={14}/></button></div></div>
            <YardMap blocks={blocks} focusId={focusedBlock?.id} scenario={scenario} layer={layer} zoom={zoom} selected={selected} block={focusedBlock?.id || block} onBlock={id => openFocus(id)} onSelect={c => setStackChoice({ blockId: c.block, bay: c.bay, row: c.row })}/>
            <div className="yd-map-legend">{t((layer === 'exceptions' ? [['#86bbae', 'No flag'], [PERISHABLE_COLOR, 'Perishable goods'], ['#729cb6', 'Customs hold'], ['#dfb566', 'Access'], ['#dba55c', 'Weight conflict'], ['#d36a58', 'Urgent care / perishable delay'], ['#9c8fbd', 'Sensor']] : layer === 'power' ? [['#5d9bba', 'Energized connection'], ['#d36a58', 'Interrupted connection'], ['#c4cdd3', 'No reefer connection']] : [[PERISHABLE_COLOR, 'Perishable goods'], ...Object.entries(CARGO_COLOR).map(([kind, color]) => [color, cargoLabel[kind as keyof typeof cargoLabel]])]).map(([color, label]) => <span key={label}><i style={{ background: color }}/>{t(label)}</span>))}<small>{t("Synthetic infrastructure \u00B7 not real LA positions")}</small></div><PowerResources blocks={focusedBlock ? [focusedBlock] : blocks} scenario={scenario} onBlock={id => { const c = [...all].filter(c => c.block === id).sort((a, b) => compareAttention(a, b, scenario))[0]; if (c)
                    selectInPlace(c); }}/>{t((focusedBlock || focus === 'yard' && mapSelectionVisible) && <StackContents block={focusedBlock || selectedBlock} selected={selected} scenario={scenario} onSelect={selectInPlace}/>)}</>)}
        </section>)}
        {t(!focusedBlock && focus !== 'yard' && <section ref={queueResults} className="yd-queue"><div className="yd-panel-title"><div><ListFilter size={17}/><h2>{t(view === 'queue' ? quadrant ? QUADRANTS[quadrant].name + ' · queue' : 'Pending action queue' : exceptionsOnly ? 'Decision queue' : 'Container inventory')}</h2><span className="yd-count">{t(number(rows.length))}</span></div><button className="yd-text-button" onClick={exportView}><ArrowDownToLine size={14}/>{t("Export view")}</button></div><div className="yd-queue-tools"><label className="yd-search"><Search size={15}/><input aria-label={t("Search demo containers")} placeholder={t("Search container, carrier or block\u2026")} value={query} onChange={e => setQuery(e.target.value)}/>{t(query && <button aria-label={t("Clear search")} onClick={() => setQuery('')}><X size={13}/></button>)}</label>{t(!focusedBlock && <label className="yd-block-filter"><Filter size={13}/><select aria-label={t("Filter yard block")} value={block} onChange={e => setBlock(e.target.value)}><option value="all">{t("All blocks")}</option>{t(blocks.map(b => <option key={b.id} value={b.id}>{t(b.id)}{t(" \u00B7 ")}{t(b.short)}</option>))}</select></label>)}<label className="yd-checkbox"><input type="checkbox" checked={exceptionsOnly} onChange={e => setExceptionsOnly(e.target.checked)}/>{t("Exceptions only")}</label>{t((!focusedBlock && block !== 'all' || query || quadrant || lookupActive) && <button className="yd-text-button" onClick={() => { setBlock('all'); setQuery(''); setQuadrant(null); setLookupActive(false); }}>{t("Clear filters")}</button>)}</div>
          {t(lookupActive && <div className="yd-filter-context"><span>{t("Current inventory query: ")}{t(lookup.containerId || 'Any number')}{t(" \u00B7 ")}{t(lookup.company || 'All carriers')}{t(" \u00B7 includes normal containers")}</span><button onClick={() => setLookupActive(false)}>{t("Clear query filter ")}<X size={12}/></button></div>)}{t(view === 'queue' && quadrant && <div className="yd-filter-context">{t("Showing pending \u201C")}{t(QUADRANTS[quadrant].name)}{t("\u201D actions. One row per action. ")}<button onClick={() => setQuadrant(null)}>{t("Show all quadrants ")}<X size={12}/></button></div>)}<div className="yd-table-scroll"><table className="yd-table"><thead><tr><th>{t("Container / cargo")}</th><th>{t("Location")}</th><th>{t("Exception")}</th><th>{t("Suggested next action")}</th><th>{t("Review")}</th><th /></tr></thead><tbody>{t(entries.slice(currentPage * 8, currentPage * 8 + 8).map(({ container: c, issue: key }) => {
                    const m = issuePresentation(c, key), change = priorityChange(c, scenario), reviewed = decisions.find(d => d.id === c.id && d.issue === key && d.scenario === scenario), task = run.jobs.find(j => j.containerId === c.id && j.issue === key);
                    return <tr key={`${c.id}:${key}`} className={selected.id === c.id && issue === key ? 'selected' : ''} onClick={() => select(c, key)}><td><button className="yd-container-button" onClick={e => { e.stopPropagation(); select(c, key); }}>{t(c.cargo === 'reefer' ? <Snowflake size={15}/> : <Box size={15}/>)}<span><b>{t(c.id)}</b><small>{t(cargoLabel[c.cargo])}{t(" \u00B7 ")}{t(c.carrier)}</small>{isPerishable(c) && <span className="yd-perishable-tag">{t("Perishable goods")}</span>}</span></button></td><td><span className="yd-location">{t(c.block)}</span><small className="yd-cell-sub">{t("Bay ")}{t(String(c.bay).padStart(2, '0'))}{t(" \u00B7 row ")}{t(c.row)}{t(" \u00B7 tier ")}{t(c.tier)}</small></td><td><span className={`yd-issue yd-level-${m.level}`}><i />{t(m.short)}</span>{key === 'congestion' && isPerishable(c) && <small className="yd-cell-sub">+{congestionExposure(c, scenario).delayMinutes} {t('min pickup delay')}</small>}{t(issuesFor(c, scenario).length > 1 && <small className="yd-cell-sub">{t("+")}{t(issuesFor(c, scenario).length - 1)}{t(" independent flag(s)")}</small>)}</td><td><span className="yd-action-name">{t(m.action)}</span>{t(key !== 'clear' && <span className="yd-quadrant-tag" style={{ color: QUADRANTS[actionFor(c, key, scenario).quadrant].color }}>{t(QUADRANTS[actionFor(c, key, scenario).quadrant].name)}</span>)}<small className="yd-cell-sub">{t(m.owner)}</small>{change.promoted && key === change.now?.issue && <small className="yd-raised-priority">{t("Raised to Do first")} · I {change.now.importance} / U {change.now.urgency}</small>}</td><td><span className={`yd-review-state ${reviewed?.choice || ''}`}>{t(task ? WORK_STAGE[task.stage].label : reviewed ? reviewed.choice === 'accepted' ? 'Accepted' : 'Dismissed' : key === 'clear' ? 'Normal inventory' : 'Needs review')}</span></td><td><ChevronRight size={15}/></td></tr>;
                }))}</tbody></table>{t(rows.length === 0 && <div className="yd-empty"><Search size={25}/><h3>{t(view === "queue" ? "No pending actions in this view" : "No matching containers")}</h3><p>{t(view === "queue" ? "Adjust the quadrant or filters, or review recorded decisions in History." : "Change the search, block or exception filter.")}</p><button className="yd-secondary" onClick={() => { setQuery(''); setBlock('all'); setQuadrant(null); setView('yard'); setExceptionsOnly(false); setLookupActive(false); }}>{t("Show inventory")}</button></div>)}</div>
          <div className="yd-pagination"><span>{t(rows.length ? `${currentPage * 8 + 1}–${Math.min(rows.length, currentPage * 8 + 8)}` : '0')}{t(" of ")}{t(number(rows.length))} {t(view === 'queue' ? 'actions' : 'records')}</span><div><button disabled={currentPage === 0} onClick={() => setPage(p => Math.max(0, p - 1))}>{t("Previous")}</button><span>{t(currentPage + 1)}{t(" / ")}{t(pages)}</span><button disabled={currentPage >= pages - 1} onClick={() => setPage(currentPage + 1)}>{t("Next")}</button></div></div>
        </section>)}
      </> : <section className="yd-history"><div className="yd-panel-title"><div><History size={17}/><h2>{t("Review history")}</h2><span className="yd-count">{t(decisions.length)}</span></div><span className="yd-small">{t("Saved in database")}</span></div>{t(decisions.length ? decisions.map((d, i) => <article key={`${d.id}-${d.scenario}-${d.issue}-${d.at}`}><span className={`yd-history-icon ${d.choice}`}><Check size={16}/></span><div><strong>{t(d.choice === 'accepted' ? 'Suggestion accepted' : 'Suggestion dismissed')} <span>{t("\u00B7 ")}{t(d.id)}</span></strong><p>{t(ISSUE[d.issue].action)}</p><small>{t(SCENARIOS[d.scenario].name)}{t(" \u00B7 ")}{t(formatTime(d.at))} {t(d.scenario !== scenario && '· Previous scenario')}</small>{t(d.note && <blockquote>{d.note}</blockquote>)}</div><span className="yd-history-number">{t(String(decisions.length - i).padStart(2, '0'))}</span></article>) : <div className="yd-empty"><ClipboardCheck size={32}/><h3>{t("No decisions recorded yet")}</h3><p>{t("Inspect a flagged container and accept or dismiss a suggestion.")}</p><button className="yd-secondary" onClick={() => navigate('yard')}>{t("Go to yard overview")}</button></div>)}</section>)}
      <footer className="yd-footer"><span><ShieldCheck size={13}/>{t("Decision support only. No equipment, gate or external message is controlled.")}</span><button disabled={saving} onClick={() => void reset()}><RotateCcw size={12}/>{t("Regenerate demo data")}</button></footer>
    </main>
    <aside className="yd-inspector" id="yd-inspector" aria-label={t("Selected container decision")}><div className="yd-inspector-heading"><span>{t("CONTAINER DETAIL")}</span><span className="yd-muted-tag">{t("DEMO")}</span></div><div className="yd-detail-title"><div className={`yd-detail-icon ${selected.cargo}`}><Box size={25}/></div><div><h2>{t(selected.id)}</h2><p>{t(cargoLabel[selected.cargo])}{t(" \u00B7 ")}{t(carrierName(selected.carrier))}{t(" (")}{t(selected.carrier)}{t(")")}</p></div></div><div className="yd-detail-location"><MapIcon size={14}/><span>{t("Block ")}<b>{t(selected.block)}</b></span><span>{t("Bay ")}{t(String(selected.bay).padStart(2, '0'))}{t(" / Row ")}{t(selected.row)}{t(" / Tier ")}{t(selected.tier)}</span></div>
      {t(departed && <div className="yd-departure-banner"><LogOut size={18}/><div><strong>{t("Gated out \u00B7 removed from current stock")}</strong><p>{t("Last position shown below. One modeled tier slot has been freed; the audit record is retained.")}</p><button className="yd-text-button" onClick={() => navigate('post')}>{t("Open post-action records ")}<ArrowRight size={13}/></button></div></div>)}<div className="yd-zone-context">{isPerishable(selected) && <span className="yd-perishable-tag">{t('Perishable goods')} · {t(selected.commodity || 'Fresh produce')}</span>}<strong>{t(selectedBlock.purpose)}</strong><span>{t(selectedBlock.flow)}</span><span>{t(selectedBlock.plugCapacity ? `${selectedBlock.plugCapacity} modeled plugs · rows 1–2 only · ${selectedBlock.circuit}` : 'No reefer plug infrastructure in this block')}</span></div>

      <div className="yd-detail-section"><h3>{t("Problem")}</h3><div className={`yd-alert-card yd-level-${meta.level}`}><span><TriangleAlert size={16}/><b>{t(meta.label)}</b></span><p>{t(issue === 'power' ? `Assigned plug ${selected.plug?.id} is on interrupted circuit ${selected.plug?.circuit}. Other circuits and nonconnected cargo are not assumed affected.` : issue === 'temperature' ? `${number(selected.temperature)}°C observed against a ${number(selected.setpoint)}°C setpoint in the fixture.` : issue === 'weight' ? `Declared ${number(selected.declared)} kg vs ${number(selected.weight)} kg in the fixture.` : issue === 'sensor' ? `No synthetic sensor report for ${selected.reported} minutes.` : issue === 'customs' ? 'A synthetic customs hold is recorded. Clearance must be confirmed by the responsible authority.' : issue === 'congestion' ? `${isPerishable(selected) ? 'Perishable cargo' : 'This container'} depends on pickup route ${selectedExposure.route}, with ${selectedExposure.delayMinutes} min of demo delay. Current location: ${selected.block}.` : departed ? 'This container has physically left the simulated yard. It is excluded from current inventory.' : 'No exception is flagged by this prototype’s fixture policy.')}</p>{issue === 'congestion' && isPerishable(selected) && <div className="yd-congestion-facts"><span>{t('Demo pickup window')}<strong>{selectedExposure.windowMinutes} {t('min')}</strong></span><span>{t('Margin after delay')}<strong>{selectedExposure.remainingMinutes} {t('min')}</strong></span></div>}</div>{t(selectedIssues.filter(key => key !== issue).map(key => <button className="yd-secondary-flag" key={key} onClick={() => setSelectedIssue(key)}><ShieldCheck size={13}/><span>{t("Also active: ")}{t(issuePresentation(selected, key).label)}{t(" \u00B7 inspect action")}</span><ChevronRight size={12}/></button>))}</div>
      <div className="yd-detail-section"><div className="yd-detail-label"><h3>{t("Suggested next action")}</h3><span><Sparkles size={12}/>{t("Server rules")}</span></div><h4 className="yd-recommendation">{t(meta.action)}</h4>{issue === 'congestion' && isPerishable(selected) && <p className="yd-congestion-problem">{t('Keep cold-chain care in place; confirm a usable pickup appointment and escalate the time-critical case to the supervisor. Resolve independent holds in parallel.')}</p>}<div className="yd-owner"><span>{t("Coordinate with")}</span><strong>{t(meta.owner)}</strong></div>{issue !== 'temperature' && <div className="yd-prerequisite"><ShieldCheck size={15}/><p>{t(meta.prerequisite)}</p></div>}</div>
      {t(selectedAction && <div className={`yd-priority-detail yd-priority-${selectedAction.quadrant}`}><span className="yd-priority-heading">{t(QUADRANTS[selectedAction.quadrant].name)}<small>{t(QUADRANTS[selectedAction.quadrant].axes)}</small></span><div className="yd-priority-meters"><span>{t("Importance ")}<b>{t(selectedAction.importance)}{t("/100")}</b><i><em style={{ width: `${selectedAction.importance}%` }}/></i></span><span>{t("Urgency ")}<b>{t(selectedAction.urgency)}{t("/100")}</b><i><em style={{ width: `${selectedAction.urgency}%` }}/></i></span></div>{t(scenario !== 'routine' && <p className="yd-priority-change">{t(routineAction ? `Routine: ${QUADRANTS[routineAction.quadrant].name} → Now: ${QUADRANTS[selectedAction.quadrant].name}` : 'New action triggered by this scenario')}<br/>{routineAction ? <>{t('Routine score')}: I {routineAction.importance} / U {routineAction.urgency}</> : t('Routine inventory · no exception action')} <ArrowRight size={12}/> {t('Now')}: I {selectedAction.importance} / U {selectedAction.urgency}</p>)}<ul>{t(selectedAction.reasons.map(r => <li key={r}>{t(r)}</li>))}</ul><button className="yd-text-button" onClick={() => { const id = selected.id, key = issue; navigate('queue'); setSelectedId(id); setSelectedIssue(key); setQuadrant(selectedAction.quadrant); }}>{t("Open action matrix ")}<ArrowRight size={12}/></button></div>)}
      <YardEvidence container={selected} issues={selectedIssues} scenario={scenario} customsCleared={run.resolutions.some(r => r.containerId === selected.id && r.issue === 'customs')}/>
      {!departed && issue !== 'clear' && <YardAssistant key={`${backend.snapshot!.runId}:${selected.id}:${issue}`} snapshot={backend.snapshot!} containerId={selected.id} issue={issue} disabled={saving}/>}
      {t(!departed && <div className="yd-review-panel"><h3>{t("Operator review")}</h3>{t(selectedJob || decision ? <div className={`yd-decision-receipt ${selectedJob ? 'accepted' : decision?.choice}`}><CheckCheck size={20}/><strong>{t(selectedJob ? WORK_STAGE[selectedJob.stage].label + ' · in Post-action' : 'Suggestion dismissed')}</strong><p>{t(selectedJob ? 'Follow the work through completion and result verification. Acceptance alone leaves the exception active.' : 'Recorded locally. Cargo status is unchanged.')}</p>{t((selectedJob?.note || decision?.note) && <blockquote>{selectedJob?.note || decision?.note}</blockquote>)}{t(selectedJob && <button className="yd-text-button" onClick={() => navigate('post')}>{t("Open post-action queue ")}<ArrowRight size={13}/></button>)}</div> : issue === 'clear' ? <div className="yd-inventory-normal"><CheckCheck size={19}/><p>{t("Normal \u00B7 in current inventory. The container continues to occupy its slot.")}</p></div> : <><label htmlFor="yd-note">{t("Review note ")}<span>{t("Optional")}</span></label><textarea id="yd-note" placeholder={t("Add a handoff note or missing condition\u2026")} rows={2} maxLength={500} value={note} onChange={e => setNote(e.target.value)}/><div className="yd-review-buttons"><button className="yd-secondary" disabled={saving} onClick={() => review('dismissed')}>{t("Dismiss")}</button><button className="yd-primary" disabled={saving} onClick={() => review('accepted')}><Check size={15}/>{t("Accept suggestion")}</button></div></>)}<small><ShieldCheck size={12}/>{t("Acceptance queues work; verification resolves it.")}</small></div>)}
      {!departed && <section className="yd-live-observation"><h3>{t('Simulate a new observation')}</h3><p>{t('Adds a server-recorded synthetic event. Existing independent holds remain active.')}</p><div>{(['customs','weight',...(selected.cargo === 'reefer' ? ['temperature','sensor'] : [])] as const).map(key => <button key={key} className="yd-secondary" disabled={saving} onClick={() => void backend.mutate({type:'observe',containerId:selected.id,issue:key as 'customs'|'weight'|'temperature'|'sensor',note:'SIMULATED observation from the yard demo controls'})}>{t(ISSUE[key as Issue].short)}</button>)}</div></section>}
      {t(!departed && <section className="yd-inventory-disposition"><h3>{t("Inventory disposition")}</h3><p>{t(blockers.length ? 'Gate-out is blocked until active exceptions and accepted work are resolved.' : 'This container stays in stock until both release permissions and physical gate-out are confirmed.')}</p><button className="yd-primary" disabled={saving || blockers.length > 0} title={t(blockers.join('; '))} onClick={() => setGateTarget(selected.id)}><LogOut size={15}/>{t("Release & gate-out")}</button>{t(blockers.length > 0 && <small>{t(blockers.join(' · '))}</small>)}</section>)}
    </aside>
    {stackChoice && <Modal title={t('Choose a container')} subtitle={`${t('Block')} ${stackChoice.blockId} · ${t('Bay')} ${String(stackChoice.bay).padStart(2, '0')} · ${t('Row')} ${stackChoice.row}`} onClose={() => setStackChoice(null)}><div className="yd-stack-picker-content"><YardStackTiers block={blocks.find(b => b.id === stackChoice.blockId)!} bay={stackChoice.bay} row={stackChoice.row} selectedId={selected.id} scenario={scenario} onSelect={c => { selectInPlace(c); setStackChoice(null); }} /></div></Modal>}
    {t(gateContainer && <GateOutModal container={gateContainer} busy={saving} error={backend.error} uncertain={backend.uncertain} onRetry={backend.retry} blockers={releaseBlockers(gateContainer, run, scenario)} onClose={() => setGateTarget(null)} onConfirm={(evidence, clearanceConfirmed, exitConfirmed) => dispatchWorkflow({ type: 'gate_out', containerId: gateContainer.id, scenario, evidence, clearanceConfirmed, exitConfirmed, at: new Date().toISOString() })}/>)}
    {t(toast && <div className="yd-toast" role="status"><Check size={17}/><span>{t(toast)}</span><button aria-label={t("Dismiss notice")} onClick={() => setToast('')}><X size={15}/></button></div>)}
    {t(guide && <Modal title={t("About this yard prototype")} subtitle={t("An interactive design study for terminal decision support.")} onClose={() => setGuide(false)}><div className="yd-guide"><p>{t("Every container, position, metric, alert and scenario is generated locally. Blocks are a schematic, not a map of a real Los Angeles terminal.")}</p><p>{t("Click a stack to preview its tiers, then choose a container. Empty block background opens a block-only workspace with the map on the left and container details on the right. Back or Escape returns to the previous view. Query searches current inventory by number and carrier.")}</p><p>{t("Explore blocks, zoom and drag the empty space between blocks, filter containers, switch disruption scenarios, and review a suggestion. Acceptance adds a Post-action task. Start work, report completion and verify evidence before resolving its exception. Independent flags remain active. Only confirmed physical gate-out removes a container from current stock and frees its tier slot.")}</p><p>{t("The yard API saves synthetic inventory, observations, decisions, task progress and gate-outs in SQLite. Changes are verified by the server. Foreground pages refresh every two seconds. The agent is called only through explicit generation in the assistant panel. No Terminal49 or equipment is called. Browser-only history from the previous prototype is retained separately and is not imported as verified evidence.")}</p><p>{t("Only designated rows have finite reefer plugs. Circuit R1 affects B01/B02; R2 in C01 stays energized. Zone purposes and capacities are invented. In Actions, the four-quadrant matrix updates per scenario, with independent importance / urgency and visible reasons.")}</p><p>{t("Choose routine, power outage, congestion or combined conditions to see the same cohort respond. This prototype is separate from the existing operations console.")}</p><button className="yd-primary" onClick={() => setGuide(false)}>{t("Explore the workspace ")}<ArrowRight size={15}/></button></div></Modal>)}
  </div>;
}
function Metric({ label, value, detail, icon, accent = false }: {
    label: string;
    value: string;
    detail: string;
    icon: React.ReactNode;
    accent?: boolean;
}) {
    const { t } = useYardLocale();
    return <div className={`yd-kpi ${accent ? 'accent' : ''}`}><div><span>{t(label)}</span>{t(icon)}</div><strong>{t(value)}</strong><small>{t(detail)}</small></div>;
}
function ZoneMetrics({ block, scenario }: {
    block: DemoBlock;
    scenario: DemoScenario;
}) {
    const { t, number } = useYardLocale();
    const s = summarize([block], scenario), p = plugSummary(block, scenario);
    return <section className="yd-kpis yd-zone-metrics" aria-label={t(`Block ${block.id} metrics`)}><Metric label={t("Containers in this block")} value={number(s.containers)} detail={t(`${block.id} only · current yard inventory`)} icon={<Box size={20}/>}/><Metric label={t("Slot utilization")} value={`${Math.round(s.containers / s.capacity * 100)}%`} detail={t(`${s.containers} / ${s.capacity} modeled slots`)} icon={<Layers3 size={20}/>}/><Metric label={t("Flagged containers")} value={number(s.exceptions)} detail={t(`${s.urgent} temperature / power flags`)} icon={<TriangleAlert size={20}/>} accent/><Metric label={t("Reefer connections")} value={p.capacity ? `${p.connected} / ${p.capacity}` : 'None'} detail={t(p.capacity ? `${block.circuit} · ${p.offline ? 'supply interrupted' : `${p.available} unoccupied energized`}` : 'No reefer plug infrastructure')} icon={<Zap size={20}/>}/></section>;
}
function StackContents({ block, selected, scenario, onSelect }: {
    block: DemoBlock;
    selected: DemoContainer;
    scenario: DemoScenario;
    onSelect: (c: DemoContainer) => void;
}) {
    const { t } = useYardLocale();
    if (selected.block !== block.id)
        return <section className="yd-stack-contents" aria-label={t("Selected container outside this block")}><div><strong>{t(selected.id)}{t(" is in block ")}{t(selected.block)}</strong><span>{t("You are still viewing ")}{t(block.id)}{t(". This selection does not change the page or this block\u2019s metrics.")}</span><button className="yd-text-button" onClick={() => document.getElementById('yd-inspector')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{t("View selected container details ")}<ArrowRight size={14}/></button></div></section>;
    return <section className="yd-stack-contents yd-stack-vertical" aria-label={t('Selected stack contents')}><div className="yd-stack-intro"><div><strong>{t('Selected stack')}</strong><span>{t('Bay')} {String(selected.bay).padStart(2, '0')} · {t('Row')} {selected.row}</span></div></div><YardStackTiers block={block} bay={selected.bay} row={selected.row} selectedId={selected.id} scenario={scenario} onSelect={onSelect} /></section>;

}
function PowerResources({ blocks, scenario, onBlock }: {
    blocks: DemoBlock[];
    scenario: DemoScenario;
    onBlock: (id: string) => void;
}) {
    const { t } = useYardLocale();
    const powered = blocks.filter(b => b.plugCapacity > 0), total = powered.reduce((n, b) => n + b.plugCapacity, 0);
    if (!powered.length)
        return <div className="yd-power-resources yd-unpowered-note"><Zap size={18}/><div><strong>{t("No reefer plug infrastructure in this block")}</strong><p>{t("A general yard slot is not a powered reefer position. Powered storage would need to be assessed in an equipped block.")}</p></div></div>;
    return <div className="yd-power-resources"><div className="yd-resource-heading"><Zap size={15}/><strong>{t("Finite reefer infrastructure")}</strong><span>{t(total)}{t(" modeled plugs \u00B7 ")}{t(powered.length)}{t(" / ")}{t(blocks.length)}{t(" blocks equipped")}</span></div><div className="yd-power-cards">{t(powered.map(b => {
            const p = plugSummary(b, scenario);
            return <button key={b.id} className={p.offline ? 'offline' : ''} onClick={() => onBlock(b.id)} aria-label={t(`Inspect power in ${b.id}`)}><span><b>{t(b.id)}</b><small>{t(b.circuit)}{t(" \u00B7 ")}{t(p.offline ? 'SUPPLY INTERRUPTED' : 'ENERGIZED')}</small></span><strong>{t(p.connected)}{t(" / ")}{t(p.capacity)} <small>{t("connections occupied")}</small></strong><span className="yd-capacity-bar"><i style={{ width: `${p.connected / p.capacity * 100}%` }}/></span><em>{t(p.offline ? `${p.affected} units without verified backup · 0 energized free plugs` : `${p.available} unoccupied energized plugs`)}</em></button>;
        }))}</div><p>{t("Only rows 1\u20132 have modeled reefer connections; other rows have none. Free capacity is not a transfer approval. Availability, compatibility, safe access and authorization must be verified.")}</p></div>;
}
function ActionMatrix({ actions, scenario, selected, onFilter, onSelect }: {
    actions: DemoAction[];
    scenario: DemoScenario;
    selected: Quadrant | null;
    onFilter: (q: Quadrant) => void;
    onSelect: (a: DemoAction) => void;
}) {
    const { t } = useYardLocale();
    return <section className="yd-action-matrix" aria-label={t("Action importance and urgency matrix")}><div className="yd-panel-title"><div><LayoutGrid size={17}/><h2>{t("Action priorities")}</h2><span className="yd-count">{t(actions.length)}{t(" pending actions")}</span></div><span className="yd-matrix-live"><i />{t("Scenario-aware")}</span></div><div className="yd-matrix-context"><strong>{t(SCENARIOS[scenario].name)}</strong><p>{t("Each action is classified independently. The same container can need urgent care and planned clearance follow-up.")}</p></div><div className="yd-matrix-axes"><span>{t("\u2191 IMPORTANCE")}</span><span>{t("URGENCY \u2190")}</span></div><div className="yd-matrix-grid">{t((['do', 'plan', 'coordinate', 'monitor'] as Quadrant[]).map(q => {
            const items = actions.filter(a => a.quadrant === q), m = QUADRANTS[q];
            return <article key={q} className={`yd-quadrant yd-quadrant-${q} ${selected === q ? 'selected' : ''}`}><button className="yd-quadrant-heading" aria-pressed={selected === q} onClick={() => onFilter(q)}><span><small>{t(m.axes)}</small><strong>{t(m.name)}</strong></span><b>{t(items.length)}</b></button><p>{t(m.instruction)}</p><div className="yd-quadrant-items">{t(items.slice(0, 3).map(a => <button key={a.id} onClick={() => onSelect(a)} aria-label={t(`Inspect ${a.issue} action for ${a.container.id}`)}><span className="yd-matrix-location">{t(a.container.block)}</span><span><strong>{t(issuePresentation(a.container, a.issue).action)}</strong><small>{t(a.container.id)}{isPerishable(a.container) && <span className="yd-perishable-tag">{t("Perishable goods")}</span>}{t(" \u00B7 I ")}{t(a.importance)}{t(" / U ")}{t(a.urgency)}</small></span><ChevronRight size={13}/></button>))}{t(items.length === 0 && <span className="yd-matrix-empty">{t("No pending actions in this quadrant for the current filters.")}</span>)}</div><button className="yd-quadrant-all" onClick={() => onFilter(q)}>{t(selected === q ? 'Clear quadrant filter' : `Show ${items.length} actions in queue`)}<ArrowRight size={13}/></button></article>;
        }))}</div><div className="yd-matrix-policy"><ShieldCheck size={14}/><p>{t("Demo policy: importance \u226570, urgency \u226560. \u201CLess important\u201D means lower operational impact of this follow-up, never permission to skip a control. Accepted/dismissed suggestions leave this pending matrix; physical flags remain.")}</p></div></section>;
}
function YardMap({ blocks, focusId, scenario, layer, zoom, selected, block, onBlock, onSelect }: {
    blocks: DemoBlock[];
    focusId?: string;
    scenario: DemoScenario;
    layer: 'exceptions' | 'cargo' | 'power';
    zoom: number;
    selected: DemoContainer;
    block: string;
    onBlock: (id: string) => void;
    onSelect: (c: DemoContainer) => void;
}) {
    const { t } = useYardLocale();
    const viewport = useRef<HTMLDivElement>(null), drag = useRef<{
        x: number;
        y: number;
        left: number;
        top: number;
        moved: boolean;
    } | null>(null);
    const focusBlock = blocks.find(b => b.id === focusId), visibleBlocks = focusBlock ? [focusBlock] : blocks;
    const mapHeight = 118 + (Math.max(...blocks.map(b => b.row)) + 1) * 164;
    const mapBounds = focusBlock ? `${19 + focusBlock.col * 286} ${63 + focusBlock.row * 164} 279 151` : `0 0 1180 ${mapHeight}`;
    useEffect(() => { if (viewport.current) {
        viewport.current.scrollLeft = 0;
        viewport.current.scrollTop = 0;
    } }, [focusId]);
    return <div className="yd-map-viewport" ref={viewport} onPointerDown={e => { if (e.button !== 0 || !viewport.current || (e.target as Element).closest('.yd-block')) {
        drag.current = null;
        return;
    } drag.current = { x: e.clientX, y: e.clientY, left: viewport.current.scrollLeft, top: viewport.current.scrollTop, moved: false }; }} onPointerMove={e => { const d = drag.current, v = viewport.current; if (!d || !v || e.buttons !== 1)
        return; const dx = e.clientX - d.x, dy = e.clientY - d.y; if (Math.abs(dx) + Math.abs(dy) > 5)
        d.moved = true; if (d.moved) {
        v.scrollLeft = d.left - dx;
        v.scrollTop = d.top - dy;
    } }} onPointerLeave={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onClickCapture={e => { if (drag.current?.moved) {
        e.preventDefault();
        e.stopPropagation();
    } drag.current = null; }}>
    <svg className="yd-yard-svg" viewBox={mapBounds} style={{ aspectRatio: focusId ? '279 / 151' : `1180 / ${mapHeight}`, width: `${zoom * 100}%`, minWidth: `${zoom * (focusId ? 560 : 600)}px` }} role="group" aria-label={t(focusId ? `Block ${focusId} enlarged stack layout` : "Synthetic yard block schematic. Open a block for more detail.")}><title>{t(focusId ? `Block ${focusId}, enlarged layout.` : `Synthetic yard layout with ${blocks.length} blocks.`)}{t(" Colors show ")}{t(layer === 'exceptions' ? 'demo exception flags' : layer === 'power' ? 'modeled reefer connections' : 'cargo types')}{t(".")}</title><defs><pattern id="yd-grid" width="16" height="16" patternUnits="userSpaceOnUse"><path d="M 16 0 L 0 0 0 16" fill="none" stroke="#e5eaed" strokeWidth=".5"/></pattern></defs><rect width="1180" height={mapHeight} fill="#f5f7f8"/><rect width="1180" height={mapHeight} fill="url(#yd-grid)"/><rect x="0" y="0" width="1180" height="46" fill="#e6edf0"/><path d="M0 46H1180" stroke="#c8d6dc"/><text x="28" y="28" className="yd-map-water">{t("WATERSIDE / BERTH APRON")}</text><text x="947" y="28" className="yd-map-coordinate">{t("SCHEMATIC \u00B7 DEMO DATA")}</text><path d={`M19 ${mapHeight - 32}H1159`} stroke="#d0d8dd" strokeWidth="25"/><path d={`M19 ${mapHeight - 32}H1159`} stroke="#fff" strokeWidth="1.5" strokeDasharray="9 9"/><text x="31" y={mapHeight - 7} className="yd-map-coordinate">{t("LANDSIDE / GATE ACCESS")}</text><text x="990" y={mapHeight - 7} className="yd-map-coordinate">{t("LAYOUT NOT TO SCALE")}</text>
      {t(visibleBlocks.map(b => {
            const x = 25 + b.col * 286, y = 69 + b.row * 164, flags = b.containers.filter(c => primaryIssue(c, scenario) !== 'clear').length;
            const doFirst = b.containers.filter(c => actionsFor(c, scenario).some(a => a.quadrant === 'do')).length;
            const affected = circuitOffline(b.circuit, scenario), restricted = ['congestion', 'combined'].includes(scenario) && ['C03', 'C04'].includes(b.id);
            const stacks = new Map<string, DemoContainer[]>();
            b.containers.forEach(c => { const key = `${c.bay}:${c.row}`; stacks.set(key, [...(stacks.get(key) || []), c]); });
            return <g key={b.id} className="yd-block" opacity={block !== 'all' && block !== b.id ? .35 : 1}><rect data-block-background={b.id} role={focusId ? undefined : "button"} tabIndex={focusId ? undefined : 0} aria-label={t(`Open block ${b.id} from empty background, ${b.containers.length} containers, ${flags} flagged`)} onClick={e => { e.stopPropagation(); onBlock(b.id); }} onKeyDown={e => { if (!focusId && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault();
                e.stopPropagation();
                onBlock(b.id);
            } }} x={x} y={y} width="267" height="139" rx="4" fill={affected ? '#fff2ee' : layer === 'power' && b.plugCapacity ? '#eef7fb' : restricted ? '#fff7e7' : '#fff'} stroke={block === b.id ? '#346b84' : affected ? '#d99889' : restricted ? '#dcc18a' : '#d7e0e5'} strokeWidth={block === b.id ? 2 : 1}/><g pointerEvents="none"><rect x={x + 1} y={y + 1} width="265" height="27" fill="transparent"/><text x={x + 12} y={y + 18} className="yd-map-block-name">{t(b.id)}</text><text x={x + 61} y={y + 18} className="yd-map-coordinate">{t(affected ? `${b.short} · ${b.circuit} OFF` : restricted ? `${b.short} · ACCESS` : b.short)}</text><text x={x + 247} y={y + 18} textAnchor="end" className="yd-map-count">{t(Math.round(b.containers.length / b.capacity * 100))}{t("%")}</text></g>
          {t(Array.from({ length: 18 }, (_, bay) => <text key={bay} x={x + 37 + bay * 12} y={y + 39} textAnchor="middle" className="yd-map-bay">{t(String(bay + 1).padStart(2, '0'))}</text>))}
          {t(Array.from({ length: 4 }, (_, row) => <text key={row} x={x + 14} y={y + 56 + row * 14} className="yd-map-bay">{t(row + 1)}</text>))}
          {t(Array.from({ length: 72 }, (_, position) => {
                    const bay = position % 18 + 1, row = Math.floor(position / 18) + 1, stack = stacks.get(`${bay}:${row}`) || [], sx = x + 31 + (bay - 1) * 12, sy = y + 48 + (row - 1) * 14;
                    if (!stack.length)
                        return <rect pointerEvents="none" key={position} x={sx} y={sy} width="10" height="9" fill={layer === 'power' && row <= b.pluggedRows ? affected ? '#fae0d9' : '#d0e9f4' : '#f0f3f4'} stroke={layer === 'power' && row <= b.pluggedRows ? '#5d9bba' : '#dde4e7'} strokeDasharray={row <= b.pluggedRows ? '2 1' : undefined} strokeWidth=".5"><title>{t(row <= b.pluggedRows ? `Equipped position · ${b.circuit} · ${b.maxTiers} modeled plug slots` : 'Unpowered position')}</title></rect>;
                    const representative = [...stack].sort((a, c) => compareAttention(a, c, scenario))[0], color = layer === 'power' ? row <= b.pluggedRows ? affected ? '#d36a58' : '#5d9bba' : '#c4cdd3' : layer === 'cargo' ? isPerishable(representative) ? PERISHABLE_COLOR : CARGO_COLOR[representative.cargo] : exceptionColor(representative, scenario);
                    const chosen = stack.some(c => c.id === selected.id), height = stack.length * 1.3;
                    return <g key={position} className="yd-stack" role="button" tabIndex={focusId ? 0 : -1} aria-label={t(`Select stack ${b.id} bay ${bay}, row ${row}, ${stack.length} containers`)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        e.stopPropagation();
                        onSelect(representative);
                    } }} onClick={e => { e.stopPropagation(); onSelect(representative); }}><title>{t(representative.id)}{t(" \u00B7 ")}{t(location(representative))}{t(" \u00B7 ")}{t(issuePresentation(representative, primaryIssue(representative, scenario)).label)}{isPerishable(representative) && t(" · Perishable goods")}{t(" \u00B7 ")}{t(stack.length)}{t(" containers in stack \u00B7 ")}{t(row <= b.pluggedRows ? `${b.circuit} reefer connections` : 'No reefer connections')}</title><rect x={sx + 1} y={sy - height + 2} width="10" height={9 + height} fill="#59766c" opacity=".35"/><rect x={sx} y={sy - height} width="10" height="9" rx=".4" fill={color} stroke={chosen ? '#122f48' : '#607b704d'} strokeWidth={chosen ? 2 : .65}/><path d={`M${sx + 2} ${sy - height + 1}v6m3-6v6m3-6v6`} stroke="#ffffff" opacity=".22" strokeWidth=".5"/>{t(chosen && <circle cx={sx + 5} cy={sy - height - 5} r="2" fill="#173d56"/>)}</g>;
                }))}<path pointerEvents="none" d={`M${x + 12} ${y + 112}h243`} stroke="#e4e9ec"/><text x={x + 12} y={y + 124} className="yd-map-count">{t(b.containers.length)}{t(" / ")}{t(b.capacity)}{t(" slots")}</text><text x={x + 12} y={y + 135} className="yd-map-infrastructure">{t(b.plugCapacity ? `${b.containers.filter(c => c.plug).length}/${b.plugCapacity} plugs occupied · rows 1–2 · ${b.circuit}` : "NO REEFER PLUGS")}</text><text x={x + 247} y={y + 128} textAnchor="end" className={flags ? 'yd-map-alert-count' : 'yd-map-count'}>{t(doFirst || flags)}{t(doFirst ? " do first" : " flagged")}</text></g>;
        }))}
    </svg>
  </div>;
}
