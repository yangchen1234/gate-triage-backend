"""Cross-language golden contracts prevent silent changes to the existing demo."""
import hashlib
import json
from pathlib import Path
import pytest
from gate_triage.yard_data import make_yard, issues_for, assess

MANIFEST=json.loads((Path(__file__).parent/'fixtures'/'yard-parity.json').read_text())
def canonical(v):
    if isinstance(v,float) and v.is_integer(): return int(v)
    if isinstance(v,list): return [canonical(x) for x in v]
    if isinstance(v,dict): return {k:canonical(value) for k,value in v.items()}
    return v

def digest(v): return hashlib.sha256(json.dumps(canonical(v),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@pytest.mark.parametrize('profile',MANIFEST['profiles'],ids=lambda p:f"{p['port']}-{p['seed']}")
def test_server_fixtures_and_priorities_match_the_original_cohort(profile):
    blocks=make_yard(profile['port'],profile['seed'])
    assert digest(blocks)==profile['fixture']
    for scenario, expected in profile['policies'].items():
        assessments=[assess(c,issue,scenario) for b in blocks for c in b['containers'] for issue in issues_for(c,scenario)]
        assert digest(assessments)==expected
