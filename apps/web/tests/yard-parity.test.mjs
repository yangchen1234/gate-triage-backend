import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { makeDemo, issuesFor, actionFor, cargoProfile } from '../src/yard-demo.ts';

const manifest=JSON.parse(readFileSync(new URL('../../../tests/fixtures/yard-parity.json',import.meta.url),'utf8'));
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const digest=v=>createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
test('TypeScript fixtures and every assessment match independently generated server contracts',()=>{
  for(const profile of manifest.profiles){
    const blocks=makeDemo(profile.seed,profile.port);
    assert.equal(digest(blocks),profile.fixture);
    const legacy=structuredClone(blocks);
    for(const b of legacy)for(const c of b.containers)for(const key of Object.keys(cargoProfile(c)))delete c[key];
    assert.equal(digest(legacy),profile.legacyFixture,'Existing physical inventory and measurements stay unchanged');
    for(const [scenario,expected] of Object.entries(profile.policies)){
      const assessments=blocks.flatMap(b=>b.containers.flatMap(c=>issuesFor(c,scenario).map(issue=>{
        const {id,container,...assessment}=actionFor(c,issue,scenario);return assessment;
      })));
      assert.equal(digest(assessments),expected,`${profile.port} / ${scenario}`);
    }
  }
});
