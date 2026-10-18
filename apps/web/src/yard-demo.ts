// Isolated UI fixtures. These numbers and positions are synthetic, not port observations.
export type DemoPort = 'la' | 'rotterdam';
export const PORTS = {
  la: { name: 'Los Angeles', language: 'English', locale: 'en-US', timeZone: 'America/Los_Angeles', seed: 27149, idPrefix: 'SIMU', serial: 2000000 },
  rotterdam: { name: 'Rotterdam', language: 'Nederlands', locale: 'nl-NL', timeZone: 'Europe/Amsterdam', seed: 44329, idPrefix: 'RTDM', serial: 4000000 },
} as const;
export type DemoScenario = 'routine' | 'power' | 'congestion' | 'combined';
export type Issue = 'clear' | 'customs' | 'weight' | 'temperature' | 'sensor' | 'power' | 'congestion';
export type Cargo = 'dry' | 'reefer' | 'hazmat' | 'empty';
export type Quadrant = 'do' | 'plan' | 'coordinate' | 'monitor';
export type PowerCircuit = 'R1' | 'R2';
export type ActionAssessment = { issue: Exclude<Issue, 'clear'>; importance: number; urgency: number; quadrant: Quadrant; reasons: string[] };
export type DemoContainer = { observationVersion?: number; lastObservedAt?: string; lastObservedSource?: string; assessments?: Partial<Record<DemoScenario, ActionAssessment[]>>; id: string; block: string; bay: number; row: number; tier: number; cargo: Cargo; carrier: string; yardStatus: 'in-yard' | 'departed'; issue: Issue; priority: number; temperature: number; setpoint: number; reported: number; weight: number; declared: number; handlingWindowMinutes: number; criticalCargo: boolean; verifiedUnitBackup?: boolean; verifiedAlternateAccess?: boolean; plug: { id: string; circuit: PowerCircuit } | null };
export type ZoneSpec = { id: string; purpose: string; short: string; maxTiers: number; pluggedRows: number; circuit: PowerCircuit | null; flow: string };
export type DemoBlock = ZoneSpec & { group: string; col: number; row: number; capacity: number; plugCapacity: number; containers: DemoContainer[] };
export type DemoDecision = { observationVersion?: number; id: string; scenario: DemoScenario; issue: Issue; choice: 'accepted' | 'dismissed'; note: string; at: string };
export type DemoAction = { id: string; container: DemoContainer; issue: Exclude<Issue, 'clear'>; importance: number; urgency: number; quadrant: Quadrant; reasons: string[] };
export type YardLookup = { containerId: string; company: string };
export const CARRIERS: Record<string, string> = { MAEU: 'Maersk', CMDU: 'CMA CGM', ONEY: 'Ocean Network Express (ONE)', MSCU: 'MSC', HLCU: 'Hapag-Lloyd' };
export function carrierName(code: string) { return CARRIERS[code] || code; }
const normalizeId = (value: string) => value.toUpperCase().replace(/[^A-Z0-9]/g, '');
export function queryYardInventory(containers: DemoContainer[], lookup: YardLookup): DemoContainer[] {
  const id = normalizeId(lookup.containerId), company = lookup.company.trim().toLowerCase().replace(/[\s-]+/g, '');
  if (lookup.containerId.trim() && !id) return [];
  return containers.filter(c => c.yardStatus === 'in-yard' && (!id || normalizeId(c.id).includes(id)) && (!company || `${c.carrier} ${carrierName(c.carrier)}`.toLowerCase().replace(/[\s-]+/g, '').includes(company))).sort((a, b) => a.id.localeCompare(b.id));
}
// Invented block capabilities: only rows 1/2 of B01, B02 and C01 have reefer connections.
export const ZONES: ZoneSpec[] = [
  { id: 'A01', purpose: 'Import storage', short: 'IMPORT', maxTiers: 4, pluggedRows: 0, circuit: null, flow: 'Vessel discharge → pickup' },
  { id: 'A02', purpose: 'Import storage', short: 'IMPORT', maxTiers: 4, pluggedRows: 0, circuit: null, flow: 'Vessel discharge → pickup' },
  { id: 'A03', purpose: 'Export staging', short: 'EXPORT', maxTiers: 4, pluggedRows: 0, circuit: null, flow: 'Gate receipt → vessel load' },
  { id: 'A04', purpose: 'Export staging', short: 'EXPORT', maxTiers: 4, pluggedRows: 0, circuit: null, flow: 'Gate receipt → vessel load' },
  { id: 'B01', purpose: 'Reefer storage', short: 'REEFER', maxTiers: 3, pluggedRows: 2, circuit: 'R1', flow: 'Powered cargo care' },
  { id: 'B02', purpose: 'Reefer storage', short: 'REEFER', maxTiers: 3, pluggedRows: 2, circuit: 'R1', flow: 'Powered cargo care' },
  { id: 'B03', purpose: 'Empty equipment', short: 'EMPTY', maxTiers: 5, pluggedRows: 0, circuit: null, flow: 'Empty return / reuse' },
  { id: 'B04', purpose: 'DG-designated storage', short: 'DG AREA', maxTiers: 2, pluggedRows: 0, circuit: null, flow: 'Compatibility review required' },
  { id: 'C01', purpose: 'Reefer reserve / buffer', short: 'REEFER BUFFER', maxTiers: 2, pluggedRows: 2, circuit: 'R2', flow: 'Capacity assessment · not reserved' },
  { id: 'C02', purpose: 'Inspection staging', short: 'INSPECTION', maxTiers: 1, pluggedRows: 0, circuit: null, flow: 'Authorized verification' },
  { id: 'C03', purpose: 'Import pickup staging', short: 'PICKUP', maxTiers: 2, pluggedRows: 0, circuit: null, flow: 'Outbound gate handoff' },
  { id: 'C04', purpose: 'Empty pickup staging', short: 'EMPTY PICKUP', maxTiers: 2, pluggedRows: 0, circuit: null, flow: 'Outbound gate handoff' },
];
// A fictional eight-block Rotterdam terminal, not a claim about real terminal boundaries.
export const ROTTERDAM_ZONES: ZoneSpec[] = ['A01', 'A03', 'B01', 'B02', 'B03', 'C01', 'C03', 'C04'].map(id => ({ ...ZONES.find(z => z.id === id)! }));
export function zonesFor(port: DemoPort) { return port === 'rotterdam' ? ROTTERDAM_ZONES : ZONES; }
export function zoneFor(id: string, port: DemoPort = 'la') { return zonesFor(port).find(z => z.id === id); }
export const SCENARIOS: Record<DemoScenario, { name: string; detail: string }> = {
  routine: { name: 'Routine operations', detail: 'Normal conditions · review day-to-day exceptions' },
  power: { name: 'Reefer circuit R1 outage', detail: 'Only connected reefers in B01/B02 lose supply; circuit R2 in C01 remains energized' },
  congestion: { name: 'Outbound congestion', detail: 'Synthetic access restriction affects blocks C03 and C04' },
  combined: { name: 'Combined disruption', detail: 'R1 power loss + C03/C04 outbound restriction · separate care from pickup' },
};
export const ISSUE: Record<Issue, { label: string; short: string; color: string; level: number; owner: string; action: string; prerequisite: string }> = {
  clear: { label: 'No flagged exception', short: 'Routine', color: '#86bbae', level: 0, owner: 'Terminal coordinator', action: 'Review pickup readiness', prerequisite: 'Verify line release, customs clearance, appointment and receiving arrangements.' },
  customs: { label: 'Recorded customs hold', short: 'Customs', color: '#dfb566', level: 1, owner: 'Broker / customs liaison', action: 'Request hold-status follow-up', prerequisite: 'The responsible authority must confirm clearance. A recommendation does not remove a hold.' },
  weight: { label: 'Declaration mismatch', short: 'Weight conflict', color: '#dba55c', level: 2, owner: 'Carrier / inspection coordinator', action: 'Request weight and identity verification', prerequisite: 'Confirm container identity, weighing basis and tare. Arrange an authorized reweigh if required.' },
  temperature: { label: 'Temperature excursion', short: 'Temperature', color: '#d36a58', level: 3, owner: 'Reefer maintenance', action: 'Request a reefer condition check', prerequisite: 'Verify the reading, power supply and cargo requirements with authorized staff.' },
  sensor: { label: 'Sensor report missing', short: 'Sensor', color: '#9c8fbd', level: 2, owner: 'Reefer maintenance', action: 'Request telemetry / unit verification', prerequisite: 'A missing report is not proof of cargo damage. Confirm the actual unit condition.' },
  power: { label: 'Reefer circuit R1 interrupted', short: 'Power loss', color: '#d36a58', level: 3, owner: 'Yard supervisor + reefer maintenance', action: 'Assess power recovery / safe transfer', prerequisite: 'Verify live capacity, compatibility, safe access and on-site approval before moving. Unoccupied plugs are not an allocation. Independent holds remain active.' },
  congestion: { label: 'Outbound access constrained', short: 'Access', color: '#dfb566', level: 2, owner: 'Gate / trucking coordinator', action: 'Review pickup sequence and appointments', prerequisite: 'Confirm which access is affected and coordinate a valid pickup window. Do not assume all gates are closed.' },
};
function random(seed: number) { let n = seed >>> 0; return () => { n = (Math.imul(n, 1664525) + 1013904223) >>> 0; return n / 4294967296; }; }
export function makeDemo(seed?: number, port: DemoPort = 'la'): DemoBlock[] {
  const profile = PORTS[port], rand = random(seed ?? profile.seed); let serial: number = profile.serial;
  return zonesFor(port).map((zone, index) => {
    const { id } = zone, containers: DemoContainer[] = [];
    for (let bay = 1; bay <= 18; bay++) for (let lane = 1; lane <= 4; lane++) {
      if (rand() < (id === 'C01' ? .5 : .075)) continue;
      const height = Math.max(1, zone.maxTiers - 2) + Math.floor(rand() * Math.min(3, zone.maxTiers));
      for (let tier = 1; tier <= height; tier++) {
        const equipped = lane <= zone.pluggedRows && zone.circuit !== null;
        const cargo: Cargo = equipped ? 'reefer' : id === 'B03' || id === 'C04' ? 'empty' : id === 'B04' ? 'hazmat' : 'dry';
        const r = rand(), issue: Issue = r < .016 ? 'customs' : r < .024 ? 'weight' : cargo === 'reefer' && r < .075 ? 'temperature' : cargo === 'reefer' && r < .19 ? 'sensor' : 'clear';
        const weight = cargo === 'empty' ? 3900 : 8500 + Math.round(rand() * 18000);
        containers.push({ id: `${profile.idPrefix}${++serial}`, block: id, bay, row: lane, tier, cargo, carrier: ['MAEU', 'CMDU', 'ONEY', 'MSCU', 'HLCU'][Math.floor(rand() * 5)], yardStatus: 'in-yard', issue,
          priority: Math.round(22 + rand() * 29 + ISSUE[issue].level * 12), temperature: issue === 'temperature' ? 7.8 : 2 + Math.round(rand() * 8) / 10, setpoint: 2,
          reported: issue === 'sensor' ? 35 + Math.floor(rand() * 100) : 3 + Math.floor(rand() * 18), weight, declared: issue === 'weight' ? Math.round(weight * .54) : weight,
          handlingWindowMinutes: 15 + Math.floor(rand() * 345), criticalCargo: cargo === 'reefer' && serial % 7 === 0,
          plug: equipped ? { id: `${id}-${bay}-${lane}-${tier}`, circuit: zone.circuit! } : null });
      }
    }
    return { ...zone, group: id[0], col: index % 4, row: Math.floor(index / 4), capacity: 18 * 4 * zone.maxTiers, plugCapacity: 18 * zone.pluggedRows * zone.maxTiers, containers };
  });
}
export function circuitOffline(circuit: PowerCircuit | null, scenario: DemoScenario) { return circuit === 'R1' && (scenario === 'power' || scenario === 'combined'); }
export function supplyFor(c: DemoContainer, scenario: DemoScenario): 'not-connected' | 'energized' | 'interrupted' | 'verified-unit-backup' { return !c.plug ? 'not-connected' : circuitOffline(c.plug.circuit, scenario) ? c.verifiedUnitBackup ? 'verified-unit-backup' : 'interrupted' : 'energized'; }
export function plugSummary(b: DemoBlock, scenario: DemoScenario) {
  const connected = b.containers.filter(c => c.plug !== null).length, offline = circuitOffline(b.circuit, scenario);
  return { capacity: b.plugCapacity, connected, affected: b.containers.filter(c => supplyFor(c, scenario) === 'interrupted').length, offline: offline ? b.plugCapacity : 0, available: offline ? 0 : b.plugCapacity - connected };
}
export function issuesFor(c: DemoContainer, scenario: DemoScenario): Issue[] {
  if (c.assessments?.[scenario]) return c.assessments[scenario]!.map(a => a.issue);
  const issues: Issue[] = c.issue === 'clear' ? [] : [c.issue];
  if (c.cargo === 'reefer' && supplyFor(c, scenario) === 'interrupted') issues.push('power');
  if (['congestion', 'combined'].includes(scenario) && ['C03', 'C04'].includes(c.block) && !c.verifiedAlternateAccess) issues.push('congestion');
  return issues.sort((a, b) => ISSUE[b].level - ISSUE[a].level || a.localeCompare(b));
}
export function primaryIssue(c: DemoContainer, scenario: DemoScenario): Issue { return issuesFor(c, scenario)[0] || 'clear'; }
export function attention(c: DemoContainer, scenario: DemoScenario): number { return Math.min(99, c.priority + (primaryIssue(c, scenario) === 'power' ? 18 : primaryIssue(c, scenario) === 'congestion' ? 9 : 0)); }
export function compareAttention(a: DemoContainer, b: DemoContainer, scenario: DemoScenario): number { return ISSUE[primaryIssue(b, scenario)].level - ISSUE[primaryIssue(a, scenario)].level || attention(b, scenario) - attention(a, scenario) || a.id.localeCompare(b.id); }
export const QUADRANTS: Record<Quadrant, { name: string; instruction: string; axes: string; color: string }> = {
  do: { name: 'Do first', instruction: 'Urgent human coordination', axes: 'Important + urgent', color: '#b75849' },
  plan: { name: 'Plan & unblock', instruction: 'Assign an owner and next review', axes: 'Important · less urgent', color: '#356d91' },
  coordinate: { name: 'Coordinate promptly', instruction: 'Route to the responsible team', axes: 'Less important · urgent', color: '#ad813c' },
  monitor: { name: 'Monitor', instruction: 'Batch follow-up and reassess', axes: 'Less important · less urgent', color: '#6b857d' },
};
// Independent axes. Cutoffs 70/60, 60-min handling window and 90-min telemetry age
// are DEMO policy parameters, not validated industry safety limits or a production SOP.
export function actionFor(c: DemoContainer, issue: Exclude<Issue, 'clear'>, scenario: DemoScenario): DemoAction {
  const assessment = c.assessments?.[scenario]?.find(a => a.issue === issue);
  if (assessment) return { ...assessment, id: `${c.id}:${issue}`, container: c };
  let importance = 40, urgency = 30;
  const reasons: string[] = [], blocked = issuesFor(c, scenario).some(i => i === 'power' || i === 'congestion');
  switch (issue) {
    case 'power': importance = 98; urgency = 98; reasons.push(`Assigned plug ${c.plug?.id} is on interrupted ${c.plug?.circuit}.`, 'Active cold-chain interruption: supervisor and maintenance review now.'); break;
    case 'temperature': importance = 95; urgency = 95; reasons.push('Observed excursion requires prompt verification; damage is not inferred.'); break;
    case 'weight': importance = 85; urgency = !blocked && c.handlingWindowMinutes <= 60 ? 85 : 40; reasons.push('Identity / weight evidence must be reconciled before dependent handling.'); break;
    case 'customs': importance = 80; urgency = !blocked && c.handlingWindowMinutes <= 60 ? 80 : 30; reasons.push('Authorized clearance is a hard prerequisite; this action is follow-up, not release.'); break;
    case 'sensor': importance = c.criticalCargo ? 80 : 45; urgency = c.reported >= 90 ? 75 : 35; reasons.push(`${c.reported} min without a report; ${c.criticalCargo ? 'higher-sensitivity' : 'standard'} demo cargo.`, 'Telemetry follow-up only; missing data does not establish loss of power.'); if (supplyFor(c, scenario) === 'interrupted') { importance = 90; urgency = 95; reasons.push('Scenario circuit outage raises verification impact and urgency.'); } break;
    case 'congestion': importance = 88; urgency = 90; reasons.push('Affected outbound block needs prompt coordination to contain queue spillback.'); break;
  }
  if (issue === 'customs' || issue === 'weight') reasons.push(blocked ? 'Pickup is also blocked by this scenario; plan prerequisite work while access/care is addressed.' : `Synthetic next handling window: ${c.handlingWindowMinutes} min (not an operational deadline).`);
  const quadrant: Quadrant = importance >= 70 ? urgency >= 60 ? 'do' : 'plan' : urgency >= 60 ? 'coordinate' : 'monitor';
  return { id: `${c.id}:${issue}`, container: c, issue, importance, urgency, quadrant, reasons };
}
export function actionsFor(c: DemoContainer, scenario: DemoScenario): DemoAction[] { return issuesFor(c, scenario).filter((i): i is Exclude<Issue, 'clear'> => i !== 'clear').map(i => actionFor(c, i, scenario)); }
export function compareActions(a: DemoAction, b: DemoAction) { return b.urgency - a.urgency || b.importance - a.importance || a.id.localeCompare(b.id); }
export function selectContainers(containers: DemoContainer[], scenario: DemoScenario, query: string, block: string, exceptions: boolean): DemoContainer[] {
  const text = query.toLowerCase().trim();
  return containers.filter(c => (block === 'all' || c.block === block) && (!exceptions || primaryIssue(c, scenario) !== 'clear') && (!text || `${c.id} ${c.block} ${c.carrier} ${c.cargo} ${issuesFor(c, scenario).map(i => ISSUE[i].label).join(' ')}`.toLowerCase().includes(text))).sort((a, b) => compareAttention(a, b, scenario));
}
export function summarize(blocks: DemoBlock[], scenario: DemoScenario) {
  const containers = blocks.flatMap(b => b.containers);
  return { containers: containers.length, capacity: blocks.reduce((n, b) => n + b.capacity, 0), exceptions: containers.filter(c => primaryIssue(c, scenario) !== 'clear').length, urgent: containers.filter(c => ISSUE[primaryIssue(c, scenario)].level === 3).length };
}
export const CARGO_COLOR: Record<Cargo, string> = { dry: '#86bbae', reefer: '#7ca9d1', hazmat: '#ac91b8', empty: '#b8c2cb' };

// Preserve physical tier addresses; vacancies are explicit and ordered top to ground.
export function stackTierSlots(block: DemoBlock, bay: number, row: number) {
  return Array.from({ length: block.maxTiers }, (_, i) => {
    const tier = block.maxTiers - i;
    return { tier, container: block.containers.find(c => c.bay === bay && c.row === row && c.tier === tier) || null };
  });
}
