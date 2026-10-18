import { ChevronRight } from 'lucide-react';
import { CARGO_COLOR, ISSUE, carrierName, primaryIssue, stackTierSlots } from './yard-demo.ts';
import type { DemoBlock, DemoContainer, DemoScenario } from './yard-demo.ts';
import { useYardLocale } from './YardLocale.tsx';

export default function YardStackTiers({ block, bay, row, selectedId, scenario, onSelect }: { block: DemoBlock; bay: number; row: number; selectedId: string; scenario: DemoScenario; onSelect: (c: DemoContainer) => void }) {
  const { t } = useYardLocale();
  return <div className="yd-tier-preview"><div className="yd-stack-tier-list" aria-label={t('Stack tiers, highest to lowest')}>{stackTierSlots(block, bay, row).map(({ tier, container: c }) => {
    const content = <><span className="yd-stack-tier-number">{t('TIER')} {tier}<small>{t(tier === 1 ? 'GROUND' : tier === block.maxTiers ? 'TOP' : '')}</small></span><svg className="yd-container-thumbnail" viewBox="0 0 80 40" aria-hidden="true"><rect x="2" y="4" width="76" height="32" rx="2" fill={c ? CARGO_COLOR[c.cargo] : '#f2f6f8'} stroke={c ? '#64899e' : '#c0d1dd'} strokeDasharray={c ? undefined : '4 3'} /><path d="M12 9v22m9-22v22m9-22v22m9-22v22m9-22v22m9-22v22m9-22v22" stroke={c ? '#ffffff80' : '#d2dee7'} /><path d="M5 36h70" stroke="#7893a6" opacity=".4" /></svg><div className="yd-stack-unit"><strong>{c ? c.id : t('Empty slot')}</strong><small>{c ? carrierName(c.carrier) : t('No container at this tier')}</small>{c && <em style={{ color: ISSUE[primaryIssue(c, scenario)].color }}>{t(ISSUE[primaryIssue(c, scenario)].short)}</em>}</div>{c && <ChevronRight size={15} />}</>;
    return c ? <button key={tier} className={c.id === selectedId ? 'selected' : ''} aria-pressed={c.id === selectedId} aria-label={t(`Select tier ${tier}, ${c.id}`)} onClick={() => onSelect(c)}>{content}</button> : <div key={tier} className="yd-stack-empty-tier" aria-label={t(`Tier ${tier}, empty slot`)}>{content}</div>;
  })}</div><div className="yd-stack-ground"><span />{t('GROUND LEVEL')}<span /></div></div>;
}
