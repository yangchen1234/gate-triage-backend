import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { Check, ChevronRight, ShieldCheck, X } from 'lucide-react';
import type { Action, Container } from './types.ts';
import { dateTime, humanize, money } from './state.ts';

export function Badge({ children, tone = '' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}><i />{children}</span>;
}
export function ActionBadge({ action }: { action: Action }) {
  return <Badge tone={{ release: 'teal', slow: 'amber', inspect: 'danger', reroute: 'violet' }[action]}>{humanize(action)}</Badge>;
}
export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon"><Check size={22} /></div><h3>{title}</h3><p>{children}</p></div>;
}
export function Modal({ title, subtitle, children, onClose, drawer = false, kicker = 'GATE TRIAGE WORKSPACE', closeLabel = 'Close dialog' }: { title: string; subtitle?: string; children: ReactNode; onClose: () => void; drawer?: boolean; kicker?: string; closeLabel?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose); closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    dialog?.querySelector<HTMLElement>('button,input,select,textarea,[tabindex="0"]')?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') { event.preventDefault(); closeRef.current(); }
      if (event.key !== 'Tab' || !dialog) return;
      const focusable = [...dialog.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex="0"]')].filter(el => el.offsetParent !== null);
      const first = focusable[0], last = focusable.at(-1);
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && document.activeElement === first) { last?.focus(); event.preventDefault(); }
      else if (!event.shiftKey && document.activeElement === last) { first.focus(); event.preventDefault(); }
    }
    document.addEventListener('keydown', onKey);
    const old = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = old; previous?.focus(); };
  }, []);
  return <div className={`modal-backdrop ${drawer ? 'drawer-backdrop' : ''}`} onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className={`modal ${drawer ? 'drawer' : ''}`} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
      <header className="modal-heading"><div><span className="section-kicker">{kicker}</span><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" aria-label={closeLabel} onClick={onClose}><X size={20} /></button></header>
      <div className="modal-body">{children}</div>
    </div>
  </div>;
}
function EvidenceItem({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return <div className="evidence-item"><span>{label}</span><strong>{value}</strong>{sub && <small>{sub}</small>}</div>;
}
export function EvidenceDrawer({ row, onClose, onAssistant }: { row: Container; onClose: () => void; onAssistant: () => void }) {
  const sources = row.sources;
  return <Modal title={row.container_id} subtitle={`${humanize(row.cargo_type)} · ${row.carrier_code} · Zone ${row.zone}`} drawer onClose={onClose}>
    <div className="drawer-status"><ActionBadge action={row.action} /><span>Priority <b>{Math.round(row.priority * 100)}</b> / 100</span></div>
    <div className="reason-card"><span className="section-kicker">WHY THIS RECOMMENDATION</span><p>{row.reason}</p><small>Advisory recommendation. Release still requires the responsible authority.</small></div>
    <h3 className="evidence-title">Four sources, one container</h3><p className="small-copy">All source observations below are synthetic records from Ryan’s demonstration dataset.</p>
    <div className="evidence-group"><h4><span>01</span> Carrier declaration</h4><div className="evidence-grid"><EvidenceItem label="Declared status" value={humanize(sources.carrier.declared_status)} /><EvidenceItem label="Declared weight" value={`${sources.carrier.declared_weight_kg.toLocaleString()} kg`} /><EvidenceItem label="Past mismatches" value={`${sources.carrier.history_mismatches_last10} / 10`} sub="Input to source trust; not a verified carrier rating" /></div></div>
    <div className="evidence-group"><h4><span>02</span> Terminal scale</h4><div className="evidence-grid"><EvidenceItem label="Measured weight" value={`${sources.scale.weight_kg.toLocaleString()} kg`} /><EvidenceItem label="Difference from declaration" value={`${Math.abs(sources.scale.weight_kg - sources.carrier.declared_weight_kg).toLocaleString()} kg`} /><EvidenceItem label="Conflict score" value={row.conflict_score.toFixed(2)} sub="Demonstration scoring, not an industry tolerance" /></div></div>
    <div className="evidence-group"><h4><span>03</span> Customs status</h4><div className="evidence-grid"><EvidenceItem label="Recorded hold" value={sources.customs.hold ? humanize(sources.customs.hold_type) : 'No recorded hold'} /><EvidenceItem label="Estimated clearance" value={`${sources.customs.est_days_to_clear} day(s)`} sub="Synthetic estimate, not authorization" /></div></div>
    <div className="evidence-group"><h4><span>04</span> Reefer telemetry</h4>{sources.reefer ? <div className="evidence-grid"><EvidenceItem label="Observed temperature" value={`${sources.reefer.temp_c}°C`} /><EvidenceItem label="Setpoint" value={`${sources.reefer.setpoint_c}°C`} /><EvidenceItem label="Last sensor report" value={`${sources.reefer.last_ping_min} min ago`} /></div> : <p className="small-copy">No reefer sensor applies to this cargo.</p>}</div>
    <div className="evidence-group"><h4>Daily fee assumptions</h4><div className="evidence-grid"><EvidenceItem label="Port component" value={money(row.port_demurrage_per_day, row.currency)} /><EvidenceItem label="Carrier component" value={money(row.carrier_demurrage_per_day, row.currency)} /><EvidenceItem label="Total model input" value={`${money(row.demurrage_per_day, row.currency)}/day`} /><EvidenceItem label="Free days remaining" value={row.free_days_left} sub="Negative values represent days overdue" /></div><p className="fine-print">Illustrative tariff profile. This is not a bill, verified contract rate, or measured cost saving.</p></div>
    {row.decision_trace && <details className="trace-details"><summary>Scoring evidence and rule trace <ChevronRight size={15} /></summary><dl className="definition-list"><div><dt>Rule</dt><dd>{row.decision_trace.rule_fired}</dd></div><div><dt>Mode</dt><dd>{humanize(row.decision_trace.mode)}</dd></div>{Object.entries(row.decision_trace.trust_at_decision).map(([key, value]) => <div key={key}><dt>{humanize(key)} trust</dt><dd>{value ?? 'Not applicable'}</dd></div>)}</dl></details>}
    <div className="drawer-footnote"><ShieldCheck size={17} /><p>Inspecting evidence does not change cargo status or contact any third party. Arrived {dateTime(row.arrived_at)}.</p></div>
    <button className="button primary full-width" onClick={onAssistant}>Open action assistant <ChevronRight size={16} /></button>
  </Modal>;
}
