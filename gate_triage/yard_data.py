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
    return blocks


def issues_for(c, scenario):
    if c['yardStatus'] != 'in-yard': return []
    issues = set(c.get('extraIssues', []))
    if c['issue'] != 'clear': issues.add(c['issue'])
    if c['cargo'] == 'reefer' and c['plug'] and c['plug']['circuit'] == 'R1' and scenario in ('power', 'combined') and not c.get('verifiedUnitBackup'): issues.add('power')
    if c['block'] in ('C03', 'C04') and scenario in ('congestion', 'combined') and not c.get('verifiedAlternateAccess'): issues.add('congestion')
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
        importance, urgency = 88, 90
        reasons = ['Affected outbound block needs prompt coordination to contain queue spillback.']
    if issue in ('weight', 'customs'):
        reasons.append('Pickup is also blocked by this scenario; plan prerequisite work while access/care is addressed.' if blocked else f"Synthetic next handling window: {c['handlingWindowMinutes']} min (not an operational deadline).")
    quadrant = ('do' if urgency >= 60 else 'plan') if importance >= 70 else ('coordinate' if urgency >= 60 else 'monitor')
    return dict(issue=issue, importance=importance, urgency=urgency, quadrant=quadrant, reasons=reasons)


def project(c, resolutions, departed=False):
    c = deepcopy(c)
    fixed = {r['issue'] for r in resolutions if r['containerId'] == c['id']}
    if c['issue'] in fixed: c['issue'] = 'clear'
    c['extraIssues'] = [i for i in c.get('extraIssues', []) if i not in fixed]
    if 'weight' in fixed: c['declared'] = c['weight']
    if 'temperature' in fixed: c['temperature'] = c['setpoint']
    if 'sensor' in fixed: c['reported'] = 0
    c.update(verifiedUnitBackup='power' in fixed, verifiedAlternateAccess='congestion' in fixed)
    if departed: c['yardStatus'] = 'departed'
    return c
