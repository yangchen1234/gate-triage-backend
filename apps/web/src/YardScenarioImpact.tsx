import { ArrowRight, TriangleAlert } from 'lucide-react';
import { actionsFor, compareActions, congestionExposure, isPerishable, priorityChange, QUADRANTS } from './yard-demo.ts';
import type { DemoContainer, DemoScenario, Issue } from './yard-demo.ts';
import { useYardLocale } from './YardLocale.tsx';
import './yard-scenario-impact.css';

export default function YardScenarioImpact({ containers, scenario, onSelect }: {
    containers: DemoContainer[];
    scenario: DemoScenario;
    onSelect: (container: DemoContainer, issue: Issue) => void;
}) {
    const { t, number } = useYardLocale();
    if (scenario === 'routine') return null;
    const baseline = containers.filter(c => actionsFor(c, 'routine').some(a => a.quadrant === 'do')).length;
    const urgent = containers.filter(c => actionsFor(c, scenario).some(a => a.quadrant === 'do')).length;
    const promoted = containers.filter(c => priorityChange(c, scenario).promoted);
    const perishables = containers.filter(c => isPerishable(c) && congestionExposure(c, scenario).affected);
    const examples = promoted.filter(isPerishable).sort((a, b) => compareActions(priorityChange(a, scenario).now!, priorityChange(b, scenario).now!)).slice(0, 3);
    const congested = scenario === 'congestion' || scenario === 'combined';
    return <section className="yd-scenario-impact" aria-label={t('Scenario priority changes')}>
        <header><TriangleAlert size={18}/><div><strong>{t(congested ? 'Congestion emergency · priorities recalculated' : 'Power emergency · priorities recalculated')}</strong><span>{t('Whole-yard impact · same containers, current server scores')}</span></div></header>
        <div className="yd-impact-metrics">
            <div><span>{t('Do-first containers')}</span><strong><small>{number(baseline)}</small> <ArrowRight size={15}/> {number(urgent)}</strong></div>
            <div><span>{t('Newly high priority')}</span><strong>+{number(promoted.length)}</strong></div>
            {congested && <><div><span>{t('Perishables delayed')}</span><strong>{number(perishables.length)}</strong></div><div><span>{t('Demo pickup delay')}</span><strong>120 <small>{t('min')}</small></strong></div></>}
        </div>
        {examples.length > 0 && <div className="yd-impact-examples">{examples.map(c => {
            const { now, routine } = priorityChange(c, scenario);
            return <button key={c.id} onClick={() => onSelect(c, now!.issue)}>
                <span><b>{c.id}</b><small>{t(c.commodity || 'Perishable goods')} · {c.block}</small></span>
                <span>{t(routine ? QUADRANTS[routine.quadrant].name : 'Routine inventory')} <ArrowRight size={12}/> <b>{t('Do first')}</b><small>I {now!.importance} / U {now!.urgency}</small></span>
            </button>;
        })}</div>}
    </section>;
}
