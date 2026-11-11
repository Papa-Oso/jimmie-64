"""Private exact-record Castle admission replay; no native/render/gameplay acceptance.
Reads the failed receipt and existing actual-Castle adapter. No game launch,
installed-file write, dependency install, or ROM export. Only writes its report.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_jimmie_surface_rails as geometry

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT/'mods/jimmie'
DEFAULT_RUN = ROOT.parent/'jimmie64-playable-grinds-20261108/build/jimmie-runs/20261108T085709851932Z-raised-rails-roomy'
CASE = 'castle_banister_roomy'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def plain(v):
    if hasattr(v, 'items'):
        pairs = list(v.items())
        if pairs and all(isinstance(k, int) for k, _ in pairs):
            return [plain(x) for _, x in sorted(pairs)]
        return {str(k): plain(x) for k, x in pairs}
    return v


def xyz(p):
    return [p[k] for k in ('x', 'y', 'z')]


class Evidence:
    def __init__(self, run):
        self.run, self.rows = run, []
        for n, line in enumerate((run/'stdout.log').read_text(errors='replace').splitlines(), 1):
            if '[raised-rails] ' not in line:
                continue
            kind, raw = line.split('[raised-rails] ', 1)[1].split(' ', 1)
            try:
                r = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if r.get('case') == CASE:
                self.rows.append((kind, n, r))
        self.traces = {r['frame']: r for k, _, r in self.rows if k == 'trace'}
        self.scan = self.traces[371]['geometry']['scan']
        self.found = next(r for k, _, r in self.rows if k == 'event' and r['frame'] == 372 and r['kind'] == 'rail-opportunity-found')
        rejected = next(r for k, _, r in self.rows if k == 'event' and r['frame'] == 373 and r['kind'] == 'rail-candidate-deferred')
        assert rejected['extra']['reason'] == 'predicted-momentum-stall'
        assert self.found['extra']['from'] == self.scan['firstPoint']
        assert self.found['extra']['to'] == self.scan['lastPoint']
        assert xyz(rejected['position']) == xyz(self.traces[372]['position'])
        self.points = {}
        for f in range(360, 372):
            s = self.traces[f].get('geometry', {}).get('scan', {})
            if s.get('indexKey') == self.scan['indexKey'] and s.get('pointCount'):
                self.points[s['pointCount']] = s['lastPoint']
        assert sorted(self.points) == list(range(1, 8))


class Replay:
    def __init__(self, e):
        self.e, self.h = e, geometry.harness()
        self.lua, self.w = self.h.lua, self.h.world
        self.p = self.h.pt(xyz(e.traces[372]['position']))
        self.p.vx = self.p.vy = self.p.vz = self.p.yaw = 0
        self.p.onGround = True
        self.q = self.h.pt(xyz(e.traces[373]['mario']))
        self.q.vx = self.q.vz = 0
        self.c = self.h.opp.new(self.w, self.lua.eval('function()qaRng=(qaRng or 0)+1;return .5 end'))
        self.c.nextProbe = self.c.nextStatus = 999  # Admission isolation; priority checked separately.
        self.ctx = self.lua.table_from(dict(frame=373, time=373/30, enabled=True, scene='castle-replay',
            area=self.lua.table(), terrain=self.lua.table(), instance=self.lua.table(), phys=self.p,
            playerInstance=self.lua.table(), player=self.q, players=self.lua.table_from([self.q]), playerGrounded=True))
        s = e.scan
        self.rail = self.lua.table_from(dict(kind='grind', a=s['firstPoint'], b=s['lastPoint'],
            entry=s['firstPoint'], exit=s['exit'], points=list(e.points.values()), visual=s['hint']['visual'],
            shapeSource=s['source'], indexKey=s['indexKey']), recursive=True)
        self.pending = self.lua.table_from(dict(rail=self.rail, time=372/30, scene=self.ctx.scene,
            area=self.ctx.area, budgetFailures=1))
        self.c.pendingRail = self.pending
        self.call = self.lua.eval('function(w,c,p,ctx)return w:transaction(function()return c:step(p,ctx)end)end')
        self.same = self.lua.eval('function(a,b)return a==b end')
        self.lua.execute('qaAudit={};qaRng=0')
        self.lua.eval("""function(w)
          for _,name in ipairs({'validateRail','arc','raisedPresentation','support','segment'}) do
            local original=w[name]
            w[name]=function(self,...)
              qaAudit[name]=(qaAudit[name] or 0)+1
              return original(self,...)
            end
          end
        end""")(self.w)
        self.rows, self.events = [], []

    def set_frame(self, f):
        self.ctx.frame, self.ctx.time = f, f/30
        now, previous, older = self.e.traces[f], self.e.traces[f-1], self.e.traces[f-2]
        for k in ('x', 'y', 'z'):
            self.q[k] = now['mario'][k]
            self.p[k] = previous['position'][k]
        self.q.vx = now['mario']['x']-previous['mario']['x']
        self.q.vz = now['mario']['z']-previous['mario']['z']
        self.p.vx = self.p.x-older['position']['x']
        self.p.vy = self.p.y-older['position']['y']
        self.p.vz = self.p.z-older['position']['z']
        self.p.onGround = True

    def step(self, f):
        self.set_frame(f)
        before, audit_before = plain(self.p), plain(self.lua.globals().qaAudit)
        out = self.call(self.w, self.c, self.p, self.ctx)
        events = [plain(e) for e in self.c.drain(self.c).values()]
        self.events.extend(events)
        audit = plain(self.lua.globals().qaAudit)
        self.rows.append(dict(frame=f, input=before, player=plain(self.q), output=plain(out),
            phys_unchanged=before == plain(self.p), events=events, budget=plain(self.w.lastBudget),
            diagnostic=plain(self.c.diagnostic), audit={k: v-audit_before.get(k, 0) for k, v in audit.items()},
            rng=self.lua.globals().qaRng, episode=self.c.episode, task=self.c.task is not None,
            nextFun=self.c.nextFun, nextFollow=self.c.nextFollow, nextProbe=self.c.nextProbe,
            retries=self.pending.entryRetries, pending_time=self.pending.time,
            pending_identity=self.same(self.c.pendingRail, self.pending), budgetFailures=self.pending.budgetFailures))
        return out

    def two_retries(self):
        assert self.step(373) is None
        assert self.step(374) is None
        assert self.pending.entryRetries == 2



def current_scanner_checks(e):
    """Separate current scanner proof and explicitly seeded ordering-only regressions."""
    checks, result = {}, {}
    h = geometry.harness()
    trace, phase_three, rail = [], None, None
    for frame in range(360, 392):
        p = h.pt(xyz(e.traces[frame-1]['position']))
        q = h.pt(xyz(e.traces[frame]['mario']))
        previous = e.traces[frame-1]['mario']
        ctx = h.lua.table_from(dict(frame=frame, epoch=0, speed=e.traces[frame]['marioSpeed'],
            forwardX=q.x-previous['x'], forwardZ=q.z-previous['z']))
        rail, diagnostic = h.run('railScan', p, q, ctx)
        scan = h.world._railScan
        trace.append(dict(frame=frame, phase=scan.phase if scan else None,
            exitIndex=scan.exitIndex if scan else None, exitSide=scan.exitSide if scan else None,
            budget=diagnostic['budget']))
        if scan is not None and scan.phase == 3 and phase_three is None:
            phase_three = plain(scan)
        if rail is not None:
            break
    checks['current_scanner_returns_recorded_cap'] = rail is not None and rail.indexKey == e.scan['indexKey'] and math.dist(xyz(rail.a), xyz(e.scan['firstPoint'])) < .001 and math.dist(xyz(rail.b), xyz(e.scan['lastPoint'])) < .001
    checks['current_scanner_prefers_player_balcony'] = rail is not None and abs(rail.exit.y-512) < .001 and math.dist(xyz(rail.exit), [-2104.195725954826,512,-1182.351631911808]) < .001
    checks['current_scanner_shared_budget_unchanged'] = all(x['budget']['calls'] <= 3000 and x['budget']['timeLimit'] == .004 and not x['budget'].get('reason') for x in trace)
    result['scan'] = trace
    result['limits'] = 'Current real scanner with recorded actor/Mario samples against existing offline Castle queries. Separate from the historical native candidate, not a native rerun or controller continuation.'
    if rail is not None:
        result['rail'] = plain(rail)
        checks['current_exit_arc_eighteen_ticks'] = rail.exitArc is not None and rail.exitArc.duration == 18
        fresh, support = h.run('support', rail.exit, 64)
        arc, flight = h.run('arc', rail.b, rail.exit, 80, q)
        checks['current_exit_independent_support_and_arc'] = fresh is not None and arc is not None and arc.duration == 18
        result['independent_exit_proof'] = dict(support=support, arc=flight)
        t = Replay(e)
        t.rail = t.lua.table_from(plain(rail), recursive=True)
        t.pending.rail = t.rail
        t.two_retries()
        out = t.step(375)
        checks['current_scanned_candidate_two_retries_then_admits'] = out is not None and out.kind == 'rail' and t.c.episode == 1 and t.pending.entryRetries == 2
        checks['current_retry_preserves_ownership_and_age'] = all(x['phys_unchanged'] and not x['task'] and x['rng'] == 0 and x['episode'] == 0 and x['pending_identity'] and x['pending_time'] == 372/30 and x['budgetFailures'] == 1 for x in t.rows[:2])
        checks['current_admission_rechecks_all_live_proofs'] = all(x['audit'].get('validateRail') == 1 and x['audit'].get('arc',0) >= 2 for x in t.rows) and t.rows[-1]['audit'].get('raisedPresentation',0) > 0 and t.rows[-1]['audit'].get('segment',0) > 0
        checks['current_admission_shared_budget_unchanged'] = all(x['budget']['calls'] <= 3000 and x['budget']['timeLimit'] == .008 and not x['budget'].get('reason') for x in t.rows)
        result['admission'] = t.rows
        result['full_journey'] = dict(performed=False, reason='Admission only; no invented motion or native follower-success claim.')
    assert phase_three is not None, 'Current scanner never reached actual candidate exit discovery'
    order_results = {}
    offsets = [(48,0),(96,0),(144,0),(192,0),(72,120),(72,-120),(72,192),(72,-192)]
    for name, raised, initial_side, expected_side in (
        ('raised_negative_crosses_positive', True, -1, -1),
        ('raised_positive_crosses_negative', True, 1, 1),
        ('normal_ledge_negative', False, -1, 1),
        ('raised_tie', True, 0, 1)):
        # Isolate enumeration by making every attempted floor unavailable. Seed a
        # copy of the real phase-three candidate, not a claimed gameplay state.
        u = geometry.harness()
        scan = u.lua.table_from(phase_three, recursive=True)
        last = scan.points[len(scan.points)]
        p = u.pt(xyz(e.traces[365]['position']))
        q = u.pt([last.x-scan.dz*20*initial_side,512,last.z+scan.dx*20*initial_side])
        scan.frame = scan.started = 700
        scan.origin = scan.previous = p
        scan.player = q
        scan.exitSide = None
        scan.exitIndex = 1
        if not raised:
            scan.visual = None
        u.world._railScan = scan
        u.lua.execute('qaExitAttempts={}')
        u.lua.eval('function(w)w.floor=function(self,x,y,z)qaExitAttempts[#qaExitAttempts+1]={x=x,y=y,z=z};return nil end end')(u.world)
        ctx = u.lua.table_from(dict(frame=701, epoch=scan.epoch, speed=0, forwardX=scan.fx, forwardZ=scan.fz))
        frozen, budgets = [], []
        for i in range(9):
            sign = initial_side if i == 0 else (-initial_side if initial_side else 1)
            q.x, q.z = last.x-scan.dz*20*sign, last.z+scan.dx*20*sign
            ctx.frame = 701+i
            out, diag = u.run('railScan', p, q, ctx)
            assert out is None
            frozen.append(scan.exitSide)
            budgets.append(diag['budget'])
        attempts = plain(u.lua.globals().qaExitAttempts)
        expected = [dict(x=last.x+scan.dx*a-scan.dz*b*expected_side,
            y=last.y+180,z=last.z+scan.dz*a+scan.dx*b*expected_side) for a,b in offsets]
        exact = len(attempts) == 8 and all(math.dist(xyz(a),xyz(b)) < 1e-8 for a,b in zip(attempts,expected))
        checks[name+'_all_eight_in_original_pairs'] = exact
        checks[name+'_preference_frozen'] = frozen[:8] == [expected_side]*8
        checks[name+'_next_candidate_clears_preference'] = frozen[8] is None and scan.phase == 1 and scan.exitIndex is None
        order_results[name] = dict(attempts=attempts, preference=frozen, final_phase=scan.phase,
            budget=budgets, limits='Seeded copy of a real exit-search state, with unavailable-floor fault injection to exhaust offsets. This tests ordering and fallback, not terrain acceptance.')
    result['ordering_unit_cases'] = order_results
    return checks, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    e = Evidence(args.run)
    geometry.install_geometry(geometry.MODEL.geo.TRIANGLES)
    checks, results = {}, {}
    r = Replay(e)
    fresh, _ = r.h.run('validateRail', r.rail, r.q)
    plan, _ = r.h.run('arc', r.p, fresh.a, 90, r.lua.table_from(dict(landingRadius=0)))
    checks['original_exact_candidate_refused'] = r.c.railKeepsUp(r.c, r.p, fresh, r.ctx, plan) == (False, 'predicted-momentum-stall')
    r.two_retries()
    checks['two_retries_no_authority_rng_cooldown_or_phys_mutation'] = all(
        x['phys_unchanged'] and not x['task'] and x['episode'] == 0 and x['rng'] == 0
        and x['nextFun'] == 0 and x['nextFollow'] == 0 and x['nextProbe'] == 999 for x in r.rows)
    checks['same_pending_age_identity_and_budget_failures'] = all(
        x['pending_identity'] and x['pending_time'] == 372/30 and x['budgetFailures'] == 1 for x in r.rows)
    checks['numeric_hint_has_no_stale_proof'] = all(r.pending.rail[k] is None for k in
        ('points', 'exitArc', 'validatedFrame', 'raisedPresentation', 'certificate', 'method'))
    checks['original_exit_and_visual_identity_retained'] = xyz(r.pending.rail.exit) == xyz(r.rail.exit) and r.same(r.pending.rail.visual, r.rail.visual)
    out = r.step(375)
    checks['exact_third_input_full_admission'] = out is not None and out.kind == 'rail' and r.c.episode == 1
    checks['each_attempt_freshly_validates_rail_and_arc'] = all(x['audit'].get('validateRail', 0) == 1 and x['audit'].get('arc', 0) >= 2 for x in r.rows)
    checks['admission_fresh_presentation_and_player_checks'] = r.rows[-1]['audit'].get('raisedPresentation', 0) > 0 and r.rows[-1]['audit'].get('segment', 0) > 0
    checks['no_query_budget_increase'] = all(x['budget']['calls'] < 3000 and x['budget']['timeLimit'] == .008 and not x['budget'].get('reason') for x in r.rows)
    results['exact_admission_replay'] = r.rows
    results['exit_follow_scope'] = dict(exit_y=e.scan['exit']['y'], admission_player_y=e.traces[375]['mario']['y'], vertical_separation=e.traces[375]['mario']['y']-e.scan['exit']['y'], limits='The retained exit is 512 units below Mario on the balcony. Admission does not prove good follower continuation or recovery; even a lower-floor landing would not establish that.')
    results['full_journey'] = dict(performed=False, reason='Raw exact actor replay ends at admission. No invented or interpolated Mario continuation is credited.')
    # Direct helper boundary checks never pretend to be full admission.
    for name, code in (
        ('max_two', 'pending.entryRetries=2'),
        ('nonraised', 'rail.visual=nil'),
        ('wrong_source', 'rail.shapeSource="old-ledge"'),
        ('missing_points', 'rail.points=nil'),
        ('too_short', 'rail.b={x=rail.points[2].x+95,y=rail.a.y,z=rail.points[2].z}'),
        ('step_too_large', 'rail.points[2]={x=rail.a.x+25,y=rail.a.y,z=rail.a.z}')):
        t = Replay(e)
        t.lua.eval('function(pending,rail)'+code+' end')(t.pending, t.rail)
        value = t.c.retryRaisedEntry(t.c, t.pending, t.rail, t.ctx)
        checks[name+'_excluded'] = value is False and t.lua.globals().qaRng == 0 and t.c.task is None
    refusals = {}
    for name in ('support', 'presentation', 'invalid_player', 'scene', 'area', 'age', 'phys', 'terrain', 'required_follow'):
        t = Replay(e)
        t.two_retries()
        if name == 'support':
            t.lua.execute('g.find_floor=function()return -11000,nil end')
        elif name == 'presentation':
            t.lua.eval('function(w)w.raisedPresentation=function(self)return self:deny("test-fresh-presentation-block")end end')(t.w)
        elif name == 'scene':
            t.ctx.scene = 'changed-scene'
        elif name in ('area', 'phys', 'terrain'):
            t.ctx[name] = t.lua.table()
        elif name == 'age':
            t.pending.time = 375/30-2
        elif name == 'required_follow':
            t.c.nextProbe = 0
            t.lua.eval('function(c)c.follow=function(self)qaRequiredFollow=true;return {kind="follow",testPriority=true}end end')(t.c)
        t.set_frame(375)
        if name == 'invalid_player':
            t.q.x = float('nan')
        before, audit_before = plain(t.p), plain(t.lua.globals().qaAudit)
        out = t.call(t.w, t.c, t.p, t.ctx)
        events = [plain(x) for x in t.c.drain(t.c).values()]
        passed = t.c.task is None and t.c.episode == 0 and t.lua.globals().qaRng == 0 and before == plain(t.p)
        if name == 'required_follow':
            passed = passed and out is not None and out.kind == 'follow' and t.lua.globals().qaRequiredFollow is True and audit_before == plain(t.lua.globals().qaAudit)
        else:
            passed = passed and out is None
        if name in ('scene', 'area', 'age', 'phys', 'terrain'):
            passed = passed and t.c.pendingRail is None
        if name == 'presentation':
            passed = passed and not any(x['kind']=='rail-entry-retry' for x in events)
        refusals[name] = dict(passed=passed, events=events, diagnostic=plain(t.c.diagnostic), lastReject=t.w.lastReject)
        checks['fresh_'+name+'_preserved'] = passed
    results['refusals'] = refusals
    # Only the named momentum refusal may queue a suffix, even when retry capacity exists.
    t = Replay(e)
    t.lua.eval('function(c)c.railKeepsUp=function()return false,"exit-outside-companion-range" end end')(t.c)
    out = t.step(373)
    checks['non_momentum_refusal_never_retries'] = out is None and t.c.pendingRail is None and not any(x['kind']=='rail-entry-retry' for x in t.events)
    added_checks, current_scanner = current_scanner_checks(e)
    checks.update(added_checks)
    results['current_scanner_player_side_exit'] = current_scanner
    report = dict(passed=all(checks.values()), checks=checks, results=results,
        evidence=dict(run=str(args.run.resolve()), stdout_sha256=sha(args.run/'stdout.log'),
            lines=[dict(kind=k, line=n, frame=row['frame']) for k,n,row in e.rows if row.get('frame') in range(360,376)],
            exact_actor_frames=[373,374,375], candidate=e.found['extra'], exit=e.scan['exit']),
        source_sha256={n:sha(MOD/n) for n in ('skate_opportunities.lua','skate_probes.lua','skate_surface_rails.lua','skate_visible_rails.lua','skate_rail_presentation.lua')},
        test_sha256=sha(Path(__file__)), adapter_sha256={str(p):sha(p) for p in (
            Path(geometry.MODEL.__file__), Path(geometry.MODEL.geo.__file__), ROOT/'tools/test_jimmie_surface_rails.py', ROOT/'tools/test_jimmie_natural_rails.py')},
        collision_sha256=geometry.MODEL.geo.META['collision_sha256'], native_acceptance=False, rendered_acceptance=False,
        limits='Exact native-recorded actor inputs replayed into current Lua against private static Castle triangles with the existing approximate wall adapter and zero clock. Pending admission and deterministic test RNG are isolated; normal gameplay lottery is unchanged. Not autonomous discovery, native timing, native locomotion, rendering, full journey or gameplay reliability. No controller continuation is credited.')
    destination = ROOT/'build/rail-entry-retry/focused.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(passed=report['passed'], checks=checks,
        calls=[x['budget']['calls'] for x in r.rows], report=str(destination)), indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
