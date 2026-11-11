"""Assert the guarded Castle replay's automatic rail journey, not a debug pose.
Reads only a supplied existing isolated run and writes a small private receipt.
The fixture uses initial actor placement and stationary Mario; this is native
moving-controller evidence, not rendered human play or physical input acceptance.
"""
from pathlib import Path
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
 if not run.is_relative_to((ROOT/'build/jimmie-runs').resolve()):p.error('Expected existing guarded fork test run')
 report=json.loads((run/'report.json').read_text());inputs=json.loads((run/'input.json').read_text());text=(run/'stdout.log').read_text(errors='replace')
 events=[];traces=[]
 for line in text.splitlines():
  for marker,target in [('[skate-opportunity] ',events),('[stock-terrain] trace ',traces)]:
   if marker in line:
    try:target.append(json.loads(line.split(marker,1)[1]))
    except json.JSONDecodeError:pass
 traces=[r for r in traces if r.get('case')=='upper_rail_natural']
 cases={c['case']:c for c in report['cases']};upper=cases.get('upper_rail_natural',{})
 landings=[e for e in events if e.get('kind')=='landing-observed' and e.get('opportunity')=='rail']
 completed=[]
 for landed in landings:
  journey=[e for e in events if e.get('episode')==landed['episode']]
  selected=next((e for e in journey if e['kind']=='selected' and e.get('opportunity')=='rail'),None)
  contact=next((e for e in journey if e['kind']=='rail-contact-observed'),None)
  exit=next((e for e in journey if e['kind']=='rail-exit'),None)
  discovery=next((e for e in reversed(events) if e['kind']=='rail-opportunity-found' and selected and e['frame']<selected['frame']),None)
  balance=[r for r in traces if contact and exit and contact['frame']<=r['frame']<=exit['frame'] and r.get('grind') and str(r.get('clip','')).startswith('balance')]
  if selected and contact and exit and discovery and balance and selected['frame']<contact['frame']<=exit['frame']<landed['frame']:
   completed.append(dict(episode=landed['episode'],discovery=discovery,selected=selected,contact=contact,exit=exit,landed=landed,balance=balance))
 checks=dict(base_regression_passed=report['passed'],actual_native_upper_grind=upper.get('hadGrind') is True,automatic_full_journey=bool(completed),grounded_landing=any(r.get('phase')=='landed' and r.get('position',{}).get('grounded') for r in traces),ordinary_grounded_handback=any(r.get('kind') is None and r.get('position',{}).get('grounded') and completed and r['frame']>completed[0]['landed']['frame'] for r in traces),east_hop_preserved=cases.get('east_late',{}).get('hadHop') is True,west_hop_preserved=cases.get('west_late',{}).get('hadHop') is True,personal_unchanged=report['checks']['personal_unchanged'],no_lua_errors=report['checks']['no_lua_errors'],source_matches=all(inputs['package_files'].get(n)==sha(ROOT/'mods/jimmie'/n) for n in ('skate_probes.lua','skate_opportunities.lua')))
 result=dict(passed=all(checks.values()),checks=checks,run=str(run),engine_sha256=report['engine_sha256'],source_sha256={n:inputs['package_files'][n] for n in ('skate_probes.lua','skate_opportunities.lua')},completed=completed,max_op_seconds=upper.get('maxOpSeconds'),limits='Windowless native geometry and ordinary moving companion after initial fixture placement, with stationary Mario and random crash misses. Not human normal-play, visual, physical-controller or listening acceptance. 4ms budget is cooperative, not a hard callback bound.')
 (run/'natural-rails.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
