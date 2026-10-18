import { useYardLocale } from './YardLocale.tsx';
import { ArrowRight, Box, Building2, ChevronLeft, ChevronRight, Search, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { carrierName, CARRIERS, ISSUE, primaryIssue } from './yard-demo.ts';
import type { DemoContainer, DemoScenario, YardLookup } from './yard-demo.ts';
type Props = {
    lookup: YardLookup;
    results: DemoContainer[];
    total: number;
    scenario: DemoScenario;
    selectedId: string;
    onChange: (lookup: YardLookup) => void;
    onSelect: (container: DemoContainer) => void;
    onShowAll: () => void;
    onClose: () => void;
};
export default function YardInventoryQuery({ lookup, results, total, scenario, selectedId, onChange, onSelect, onShowAll, onClose }: Props) {
    const { t, number } = useYardLocale();
    const [page, setPage] = useState(0);
    const pageSize = 6, pages = Math.max(1, Math.ceil(results.length / pageSize)), current = Math.min(page, pages - 1);
    useEffect(() => { setPage(0); }, [lookup.containerId, lookup.company]);
    const filtered = Boolean(lookup.containerId || lookup.company);
    return <aside className="yd-inventory-query" aria-label={t("Current yard inventory query")}>
    <div className="yd-query-heading"><div><Search size={17}/><strong>{t("Find containers")}</strong></div><button aria-label={t("Close inventory query")} onClick={onClose}><X size={16}/></button></div>
    <div className="yd-query-description"><span className="yd-query-live"><i />{t("CURRENT YARD INVENTORY")}</span></div>
    <form className="yd-query-fields" onSubmit={e => { e.preventDefault(); onShowAll(); }}>
      <label htmlFor="yd-query-number">{t("Container number")}</label><div className="yd-query-input"><Box size={14}/><input id="yd-query-number" placeholder={t("Full or partial number")} value={lookup.containerId} onChange={e => onChange({ ...lookup, containerId: e.target.value })} autoComplete="off"/></div>
      <label htmlFor="yd-query-company">{t("Company / carrier")}</label><div className="yd-query-input"><Building2 size={14}/><input id="yd-query-company" placeholder={t("e.g. Maersk or MAEU")} list="yd-carrier-options" value={lookup.company} onChange={e => onChange({ ...lookup, company: e.target.value })} autoComplete="off"/><datalist id="yd-carrier-options">{t(Object.entries(CARRIERS).map(([code, name]) => <option key={code} value={code}>{t(name)}</option>))}</datalist></div>
      <div className="yd-query-count"><strong>{t(number(results.length))}</strong><span>{t("matching / ")}{t(number(total))}{t(" in yard")}</span>{t(filtered && <button type="button" onClick={() => onChange({ containerId: '', company: '' })}>{t("Clear")}</button>)}</div>
      <button type="submit" className="yd-query-show" disabled={!results.length}>{t("Show matching inventory ")}<ArrowRight size={13}/></button>
    </form>
    <div className="yd-query-results" aria-label={t("Container query results")} aria-live="polite">{t(results.slice(current * pageSize, current * pageSize + pageSize).map(c => {
            const flag = primaryIssue(c, scenario);
            return <button key={c.id} className={selectedId === c.id ? 'selected' : ''} onClick={() => onSelect(c)} aria-label={t(`Locate ${c.id} in block ${c.block}`)}><span className="yd-query-result-top"><strong>{t(c.id)}</strong><b>{t(c.block)}</b></span><span>{t(carrierName(c.carrier))} <small>{t("\u00B7 ")}{t(c.carrier)}</small></span><span className="yd-query-result-bottom"><small>{t("Bay ")}{t(String(c.bay).padStart(2, '0'))}{t(" \u00B7 row ")}{t(c.row)}{t(" \u00B7 tier ")}{t(c.tier)}</small><i style={{ background: ISSUE[flag].color }} title={t(ISSUE[flag].label)}/></span></button>;
        }))}{t(!results.length && <div className="yd-query-empty"><Search size={23}/><strong>{t("No containers found")}</strong><p>{t("Try a shorter number, carrier name or code. Both fields must match when filled.")}</p></div>)}</div>
    <div className="yd-query-pagination"><button aria-label={t("Previous query results")} disabled={current === 0} onClick={() => setPage(p => Math.max(0, p - 1))}><ChevronLeft size={15}/></button><span>{t(results.length ? `${current * pageSize + 1}–${Math.min(results.length, current * pageSize + pageSize)}` : '0')}{t(" of ")}{t(number(results.length))}</span><button aria-label={t("Next query results")} disabled={current >= pages - 1} onClick={() => setPage(current + 1)}><ChevronRight size={15}/></button></div>
  </aside>;
}
