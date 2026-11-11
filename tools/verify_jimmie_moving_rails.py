"""Verify native input-driven rail journeys separately from scripted mechanics."""
from pathlib import Path
import argparse,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
 if not run.is_relative_to((ROOT/'build/jimmie-runs').resolve()):raise SystemExit('Run must belong to this checkout')
 inputs=json.loads((run/'input.json').read_text());native=json.loads((run/'report.json').read_text());lines=(run/'stdout.log').read_text(errors='replace').splitlines()
 cases={};current=None
 for line in lines:
  for marker in ('[moving-rails] placement ','[moving-rails] trace ','[moving-rails] case-end ','[skate-opportunity] '):
   if marker not in line:continue
   try:e=json.loads(line.split(marker,1)[1])
   except json.JSONDecodeError:continue
   if marker=='[moving-rails] placement ':
    current=e['case'];cases[current]=dict(placement=e,events=[],traces=[])
   elif current and marker=='[moving-rails] trace ':cases[current]['traces'].append(e)
   elif current and marker=='[moving-rails] case-end ':cases[current]['end']=e;current=None
   elif current and marker=='[skate-opportunity] ':cases[current]['events'].append(e)
   break
 checks=dict(native_report_passed=native['passed'],native_controller_routes=inputs.get('native_controller_routes') is True,not_seeded_contact=inputs.get('controlled_rail_contact') is False,normal_crash_not_overridden=not inputs.get('forced_outcome_miss_in_terrain') and not inputs.get('forced_outcome_miss_in_rail_physics'))
 checks['exact_runtime_sources']=all(inputs['package_files'].get(n)==hashlib.sha256((ROOT/'mods/jimmie'/n).read_bytes()).hexdigest() for n in ('skate_probes.lua','skate_opportunities.lua','skate_rail_index.lua'))
 journeys=[]
 for name in ('east_parallel','west_parallel','center_stairs'):
  c=cases.get(name,{});checks[name+'_native_movement']=c.get('end',{}).get('nativeMovement') is True
  checks[name+'_grounded_settling']=c.get('end',{}).get('settled') is True and c.get('end',{}).get('final',{}).get('grounded') is True
  episodes={};complete=[]
  for e in c.get('events',[]):
   kind=e['kind'];ep=e.get('episode')
   if kind=='selected' and e.get('opportunity')=='rail':episodes[ep]={'selected':e}
   if ep not in episodes:continue
   if kind in ('rail-contact-observed','rail-exit','landing-observed'):episodes[ep][kind]=e
  for ep,events in episodes.items():
   if not all(k in events for k in ('selected','rail-contact-observed','rail-exit','landing-observed')):continue
   frames=[events[k]['frame'] for k in ('selected','rail-contact-observed','rail-exit','landing-observed')]
   if frames!=sorted(frames) or frames[1]>c.get('end',{}).get('routeCutoffFrame',-1):continue
   samples=[t for t in c.get('traces',[]) if frames[1]<=t['frame']<=frames[2] and t.get('grind') is True and t.get('marioSpeed',0)>=8 and str(t.get('clip','')).startswith('balance') and t.get('bodyAnim') is not None and t.get('bodyAnim')==t.get('boardAnim')]
   if not samples:continue
   complete.append(dict(episode=ep,selected=frames[0],contact=frames[1],exit=frames[2],landed=frames[3],contact_ticks=frames[2]-frames[1]+1,moving_balance_samples=[dict(frame=t['frame'],clip=t['clip'],body=t['bodyAnim'],board=t['boardAnim'],mario_speed=t['marioSpeed']) for t in samples]))
  checks[name+'_moving_articulated_journey']=bool(complete);journeys.append(dict(case=name,journeys=complete))
 report=dict(passed=all(checks.values()),checks=checks,run=str(run),engine_sha256=inputs['engine_sha256'],runtime_sources={n:inputs['package_files'][n] for n in ('skate_probes.lua','skate_opportunities.lua','skate_rail_index.lua')},journeys=journeys,limits='Hidden actual engine with synthetic native analog/jump input after one initial placement per route. No held Mario positions/velocities, seeded rail or outcome override. Not human normal-play, rendered visibility, camera, audio or broad all-map acceptance. Prior failed runs are retained.')
 (run/'moving-rails-verified.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
