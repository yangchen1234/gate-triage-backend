import { TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';
import type { DemoContainer, DemoScenario, Issue } from './yard-demo.ts';
import { congestionExposure, issuePresentation, pickupWindowDays, SCENARIOS, supplyFor } from './yard-demo.ts';
import { useYardLocale } from './YardLocale.tsx';
import './yard-evidence.css';

export default function YardEvidence({ container, issues, scenario, customsCleared }: {
    container: DemoContainer;
    issues: Issue[];
    scenario: DemoScenario;
    customsCleared: boolean;
}) {
    const { t, number, formatTime } = useYardLocale();
    const weightConflict = issues.includes('weight');
    const temperatureConflict = issues.includes('temperature');
    const held = issues.includes('customs');
    const sensorMissing = issues.includes('sensor');
    const powerInterrupted = issues.includes('power');
    const accessConstrained = issues.includes('congestion');
    const exposure = congestionExposure(container, scenario);
    const weightDelta = (container.weight - container.declared) / 1000;
    const temperatureDelta = container.temperature - container.setpoint;
    const signed = (n: number) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${number(Math.abs(n))}`;

    function badge(label: string) {
        return <span className="yd-evidence-status"><TriangleAlert size={13} aria-hidden="true"/>{t(label)}</span>;
    }

    return <section className="yd-detail-section yd-evidence-panel" aria-labelledby="yd-evidence-title">
        <div className="yd-evidence-heading"><h3 id="yd-evidence-title">{t('Evidence snapshot')}</h3>
            <span className={`yd-evidence-count ${issues.length ? 'has-flags' : ''}`}>
                {issues.length ? `${number(issues.length)} ${t(issues.length === 1 ? 'active flag' : 'active flags')}` : t('No active flags')}
            </span>
        </div>
        <dl className="yd-evidence-comparisons">
            <div className={`yd-evidence-card ${weightConflict ? 'is-conflict' : ''}`}>
                <dt><span>{t('Declared / measured')}</span>{weightConflict && badge('Weight mismatch')}</dt>
                <dd>
                    <div className="yd-evidence-pair">
                        <div><span>{t('Declared')}</span><strong>{number(container.declared / 1000)} <small>t</small></strong></div>
                        <div><span>{t('Measured')}</span><strong className={weightConflict ? 'yd-evidence-abnormal' : ''}>{number(container.weight / 1000)} <small>t</small></strong></div>
                    </div>
                    {weightConflict && <p className="yd-evidence-delta">{t('Difference from declaration')} <b>{signed(weightDelta)} t</b></p>}
                </dd>
            </div>
            {container.cargo === 'reefer' && <div className={`yd-evidence-card ${temperatureConflict ? 'is-conflict' : ''}`}>
                <dt><span>{t('Observed / setpoint')}</span>{temperatureConflict && badge('Temperature deviation')}</dt>
                <dd>
                    <div className="yd-evidence-pair">
                        <div><span>{t('Observed')}</span><strong className={temperatureConflict ? 'yd-evidence-abnormal' : ''}>{number(container.temperature)} <small>°C</small></strong></div>
                        <div><span>{t('Setpoint')}</span><strong>{number(container.setpoint)} <small>°C</small></strong></div>
                    </div>
                    {temperatureConflict && <p className="yd-evidence-delta">{t('Difference from setpoint')} <b>{signed(temperatureDelta)} °C</b></p>}
                </dd>
            </div>}
            <div className={`yd-evidence-card yd-evidence-single ${held ? 'is-restricted' : ''}`}>
                <dt><span>{t('Customs hold')}</span>{held && badge('Release blocked')}</dt>
                <dd>{t(held ? 'Recorded · remains active' : customsCleared ? 'Verified cleared · demo' : 'None in fixture')}</dd>
            </div>
            {container.cargo === 'reefer' && <>
                <div className={`yd-evidence-card yd-evidence-single ${sensorMissing ? 'is-missing' : ''}`}>
                    <dt><span>{t('Last report')}</span>{sensorMissing && badge('Report missing')}</dt>
                    <dd>{number(container.reported)} {t('min ago')}</dd>
                </div>
                <div className={`yd-evidence-card yd-evidence-single ${powerInterrupted ? 'is-conflict' : ''}`}>
                    <dt><span>{t('Reefer supply')}</span>{powerInterrupted && badge('Power interrupted')}</dt>
                    <dd className={powerInterrupted ? 'yd-evidence-abnormal' : ''}>{t(supplyFor(container, scenario))}</dd>
                </div>
            </>}
            {accessConstrained && <div className="yd-evidence-card yd-evidence-single is-restricted">
                <dt><span>{t(issuePresentation(container, 'congestion').label)}</span>{badge('Shared exit delay')}</dt>
                <dd>{exposure.route} · +{exposure.delayDays} {t(exposure.delayDays === 1 ? 'day pickup delay' : 'days pickup delay')}</dd>
            </div>}
        </dl>
        <dl className="yd-evidence-context">
            <EvidenceContext label="Cargo profile">{t(container.commodity || 'General cargo')}</EvidenceContext>
            <EvidenceContext label="Source">{t('Server database · synthetic observations')}</EvidenceContext>
            <EvidenceContext label="Assigned reefer plug">{t(container.plug ? `${container.plug.id} · ${container.plug.circuit}` : 'None · no connection assigned')}</EvidenceContext>
            <EvidenceContext label="Handling window">{number(pickupWindowDays(container))} {t('days · demo only')}</EvidenceContext>
            <EvidenceContext label="Observation version">{number(container.observationVersion || 0)}</EvidenceContext>
            {container.lastObservedAt && <EvidenceContext label="Last observation">{formatTime(container.lastObservedAt)}</EvidenceContext>}
            <EvidenceContext label="Scenario">{t(SCENARIOS[scenario].name)}</EvidenceContext>
        </dl>
    </section>;
}

function EvidenceContext({ label, children }: { label: string; children: ReactNode }) {
    const { t } = useYardLocale();
    return <div><dt>{t(label)}</dt><dd>{children}</dd></div>;
}
