"""Server-owned synthetic yard fixtures and deterministic advisory policy.

The legacy Ryan queue remains independent: zone A/B has no known bay/row/tier
mapping. These layouts never imply a verified physical mapping of that feed.
"""
from __future__ import annotations
from copy import deepcopy
from math import floor

PORTS = {
    'la': dict(name='Los Angeles', locale='en-US', timeZone='America/Los_Angeles', seed=27149, prefix='SIMU', serial=2000000),
    'rotterdam': dict(name='Rotterdam', locale='nl-NL', timeZone='Europe/Amsterdam', seed=44329, prefix='RTDM', serial=4000000),
}
CARRIERS = {'MAEU': 'Maersk', 'CMDU': 'CMA CGM', 'ONEY': 'Ocean Network Express (ONE)', 'MSCU': 'MSC', 'HLCU': 'Hapag-Lloyd'}
ZONES = [
    ('A01', 'Import storage', 'IMPORT', 4, 0, None, 'Vessel discharge → pickup'),
    ('A02', 'Import storage', 'IMPORT', 4, 0, None, 'Vessel discharge → pickup'),
    ('A03', 'Export staging', 'EXPORT', 4, 0, None, 'Gate receipt → vessel load'),
    ('A04', 'Export staging', 'EXPORT', 4, 0, None, 'Gate receipt → vessel load'),
    ('B01', 'Reefer storage', 'REEFER', 3, 2, 'R1', 'Powered cargo care'),
    ('B02', 'Reefer storage', 'REEFER', 3, 2, 'R1', 'Powered cargo care'),
    ('B03', 'Empty equipment', 'EMPTY', 5, 0, None, 'Empty return / reuse'),
    ('B04', 'DG-designated storage', 'DG AREA', 2, 0, None, 'Compatibility review required'),
    ('C01', 'Reefer reserve / buffer', 'REEFER BUFFER', 2, 2, 'R2', 'Capacity assessment · not reserved'),
    ('C02', 'Inspection staging', 'INSPECTION', 1, 0, None, 'Authorized verification'),
    ('C03', 'Import pickup staging', 'PICKUP', 2, 0, None, 'Outbound gate handoff'),
    ('C04', 'Empty pickup staging', 'EMPTY PICKUP', 2, 0, None, 'Outbound gate handoff'),
]
LEVEL = {'clear': 0, 'customs': 1, 'weight': 2, 'temperature': 3, 'sensor': 2, 'power': 3, 'congestion': 2}
LABEL = {'customs': 'Recorded customs hold', 'weight': 'Declaration mismatch', 'temperature': 'Temperature excursion', 'sensor': 'Sensor report missing', 'power': 'Reefer circuit R1 interrupted', 'congestion': 'Outbound access constrained'}
STAGES = {'queued': 'Queued', 'in_progress': 'In progress', 'awaiting_verification': 'Verify result', 'resolved': 'Resolved'}
POLICY_VERSION = 'yard-v2-congestion'
CONGESTION_DELAY_MINUTES = 120  # Scenario input, not a measured travel time or cargo shelf life.


def cargo_profile(c):
    """Deterministic demo enrichment also supports already-persisted v1 observations.

    No RNG calls: identity, positions, measurements and existing audit stay intact.
    Refrigerated does not imply perishable: every fifth reefer models pharmaceuticals.
    """
    serial = int(''.join(ch for ch in c['id'] if ch.isdigit()) or '0')
    perish = c['cargo'] == 'reefer' and serial % 5 != 0
    commodity = ('Fresh produce' if serial % 2 else 'Seafood') if perish else 'Pharmaceuticals' if c['cargo'] == 'reefer' else 'Empty equipment' if c['cargo'] == 'empty' else 'General cargo'
    route = 'PICKUP-1' if c['block'] in ('A01', 'A02', 'B01', 'B02', 'C01', 'C03') else 'EMPTY-2' if c['block'] == 'C04' else None
    return dict(perishable=perish, commodity=commodity, outboundRoute=route, cargoProfileSource='demo_profile_v2')


def congestion_exposure(c, scenario):
    profile = cargo_profile(c)
    affected = scenario in ('congestion', 'combined') and bool(profile['outboundRoute']) and not c.get('verifiedAlternateAccess') and c['yardStatus'] == 'in-yard'
    delay = CONGESTION_DELAY_MINUTES if affected else 0
    return dict(affected=affected, route=profile['outboundRoute'], delayMinutes=delay,
                windowMinutes=c['handlingWindowMinutes'], remainingMinutes=c['handlingWindowMinutes'] - delay,
                direct=c['block'] in ('C03', 'C04'), perishable=profile['perishable'])


def make_yard(port='la', seed=None):
    profile = PORTS[port]
    n = profile['seed'] if seed is None else seed
    serial = profile['serial']
    def rand():
        nonlocal n
        n = (n * 1664525 + 1013904223) & 0xffffffff
        return n / 4294967296
    def js_round(value): return floor(value + .5)
    zones = ZONES if port == 'la' else [z for z in ZONES if z[0] in ['A01', 'A03', 'B01', 'B02', 'B03', 'C01', 'C03', 'C04']]
    blocks = []
    for index, (bid, purpose, short, tiers, plugged_rows, circuit, flow) in enumerate(zones):
        containers = []
        for bay in range(1, 19):
            for row in range(1, 5):
                if rand() < (.5 if bid == 'C01' else .075): continue
                height = max(1, tiers - 2) + floor(rand() * min(3, tiers))
                for tier in range(1, height + 1):
                    equipped = row <= plugged_rows and circuit is not None
                    cargo = 'reefer' if equipped else 'empty' if bid in ('B03', 'C04') else 'hazmat' if bid == 'B04' else 'dry'
                    r = rand()
                    issue = 'customs' if r < .016 else 'weight' if r < .024 else 'temperature' if cargo == 'reefer' and r < .075 else 'sensor' if cargo == 'reefer' and r < .19 else 'clear'
                    weight = 3900 if cargo == 'empty' else 8500 + js_round(rand() * 18000)
                    serial += 1
                    carrier = list(CARRIERS)[floor(rand() * 5)]
                    priority = js_round(22 + rand() * 29 + LEVEL[issue] * 12)
                    temp = 7.8 if issue == 'temperature' else 2 + js_round(rand() * 8) / 10
                    reported = 35 + floor(rand() * 100) if issue == 'sensor' else 3 + floor(rand() * 18)
                    window = 15 + floor(rand() * 345)
                    containers.append(dict(id=f"{profile['prefix']}{serial}", block=bid, bay=bay, row=row, tier=tier, cargo=cargo,
                        carrier=carrier, yardStatus='in-yard', issue=issue, priority=priority, temperature=temp, setpoint=2,
                        reported=reported, weight=weight, declared=js_round(weight * .54) if issue == 'weight' else weight,
                        handlingWindowMinutes=window, criticalCargo=cargo == 'reefer' and serial % 7 == 0,
                        plug=dict(id=f'{bid}-{bay}-{row}-{tier}', circuit=circuit) if equipped else None))
        blocks.append(dict(id=bid, purpose=purpose, short=short, maxTiers=tiers, pluggedRows=plugged_rows, circuit=circuit, flow=flow,
            group=bid[0], col=index % 4, row=index // 4, capacity=18 * 4 * tiers, plugCapacity=18 * plugged_rows * tiers, containers=containers))
    for b in blocks:
        for c in b['containers']: c.update(cargo_profile(c))
    return blocks


def issues_for(c, scenario):
    if c['yardStatus'] != 'in-yard': return []
    issues = set(c.get('extraIssues', []))
    if c['issue'] != 'clear': issues.add(c['issue'])
    if c['cargo'] == 'reefer' and c['plug'] and c['plug']['circuit'] == 'R1' and scenario in ('power', 'combined') and not c.get('verifiedUnitBackup'): issues.add('power')
    exposure = congestion_exposure(c, scenario)
    if exposure['affected'] and (exposure['direct'] or exposure['perishable']): issues.add('congestion')
    return sorted(issues, key=lambda i: (-LEVEL[i], i))


def assess(c, issue, scenario):
    importance, urgency, reasons = 40, 30, []
    blocked = bool(set(issues_for(c, scenario)) & {'power', 'congestion'})
    if issue == 'power':
        importance, urgency = 98, 98
        reasons = [f"Assigned plug {c['plug']['id']} is on interrupted {c['plug']['circuit']}.", 'Active cold-chain interruption: supervisor and maintenance review now.']
    elif issue == 'temperature':
        importance, urgency = 95, 95
        reasons = ['Observed excursion requires prompt verification; damage is not inferred.']
    elif issue == 'weight':
        importance, urgency = 85, 85 if not blocked and c['handlingWindowMinutes'] <= 60 else 40
        reasons = ['Identity / weight evidence must be reconciled before dependent handling.']
    elif issue == 'customs':
        importance, urgency = 80, 80 if not blocked and c['handlingWindowMinutes'] <= 60 else 30
        reasons = ['Authorized clearance is a hard prerequisite; this action is follow-up, not release.']
    elif issue == 'sensor':
        importance, urgency = 80 if c['criticalCargo'] else 45, 75 if c['reported'] >= 90 else 35
        reasons = [f"{c['reported']} min without a report; {'higher-sensitivity' if c['criticalCargo'] else 'standard'} demo cargo.", 'Telemetry follow-up only; missing data does not establish loss of power.']
        if 'power' in issues_for(c, scenario):
            importance, urgency = 90, 95
            reasons.append('Scenario circuit outage raises verification impact and urgency.')
    elif issue == 'congestion':
        exposure = congestion_exposure(c, scenario)
        if exposure['perishable']:
            importance = 94 if c['criticalCargo'] else 90
            urgency = 96 if exposure['remainingMinutes'] <= 0 else 90 if exposure['remainingMinutes'] <= 60 else 78 if exposure['remainingMinutes'] <= 180 else 65
            reasons = ['Perishable cargo depends on the congested pickup corridor, including units still in reefer storage.',
                       f"Demo delay {exposure['delayMinutes']} min versus pickup window {exposure['windowMinutes']} min; remaining margin {exposure['remainingMinutes']} min.",
                       'Confirm cold-chain care and coordinate an authorized pickup alternative; delay alone does not establish spoilage.']
        else:
            importance, urgency = (65, 75) if c['cargo'] == 'empty' else (78, 82)
            reasons = ['Affected outbound block needs prompt coordination to contain queue spillback.']
    exposure = congestion_exposure(c, scenario)
    if exposure['affected'] and exposure['perishable'] and issue in ('customs', 'weight', 'sensor'):
        importance = max(importance, 92 if c['criticalCargo'] else 88)
        urgency = max(urgency, 92 if exposure['remainingMinutes'] <= 60 else 78)
        reasons.append('Congestion raises the consequence and urgency of this perishable prerequisite; responsible staff must reconcile it without bypassing the control.')
    if issue in ('weight', 'customs'):
        reasons.append('Pickup is also blocked by this scenario; plan prerequisite work while access/care is addressed.' if blocked else f"Synthetic next handling window: {c['handlingWindowMinutes']} min (not an operational deadline).")
    quadrant = ('do' if urgency >= 60 else 'plan') if importance >= 70 else ('coordinate' if urgency >= 60 else 'monitor')
    return dict(issue=issue, importance=importance, urgency=urgency, quadrant=quadrant, reasons=reasons)


def project(c, resolutions, departed=False):
    c = deepcopy(c)
    c.update(cargo_profile(c))
    fixed = {r['issue'] for r in resolutions if r['containerId'] == c['id']}
    if c['issue'] in fixed: c['issue'] = 'clear'
    c['extraIssues'] = [i for i in c.get('extraIssues', []) if i not in fixed]
    if 'weight' in fixed: c['declared'] = c['weight']
    if 'temperature' in fixed: c['temperature'] = c['setpoint']
    if 'sensor' in fixed: c['reported'] = 0
    c.update(verifiedUnitBackup='power' in fixed, verifiedAlternateAccess='congestion' in fixed)
    if departed: c['yardStatus'] = 'departed'
    return c
