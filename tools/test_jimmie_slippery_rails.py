"""Pure Lua pace/admission/live integration, no engine or personal-file writes."""
from pathlib import Path
import json
from lupa.lua53 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


def main():
    lua = LuaRuntime(unpack_returned_tuples=True)
    o = lua.execute((ROOT / 'mods/jimmie/skate_opportunities.lua').read_text())
    point = lambda x=0, y=0, z=0, vx=0, vz=0: lua.table_from(dict(x=x, y=y, z=z, vx=vx, vz=vz))
    rail = lua.table_from(dict(a=point(), b=point(240), exit=point(270)))
    p = point()
    checks = {}
    pace = lambda m: o.railPace(rail, p, m)
    checks['stationary_no_assist'] = pace(point(100)) is None
    checks['opposing_no_assist'] = pace(point(100, vx=-20)) is None
    checks['perpendicular_no_assist'] = pace(point(100, vz=20)) is None
    checks['ahead_no_assist'] = pace(point(-1, vx=20)) is None
    checks['lateral_no_assist'] = pace(point(100, z=281, vx=20)) is None
    checks['height_no_assist'] = pace(point(100, y=221, vx=20)) is None
    checks['far_no_assist'] = pace(point(801, vx=20)) is None
    checks['catchup_continues_651'] = pace(point(651, vx=20)) is not None
    checks['catchup_continues_800'] = pace(point(800, vx=20)) is not None
    checks['invalid_velocity_no_assist'] = pace(point(100, vx=float('nan'))) is None
    checks['walking_pace'] = 0 < pace(point(100, vx=8)) <= 16
    checks['run_gap_target_tapers'] = pace(point(300, vx=32)) > pace(point(20, vx=32))
    moving = point(120, vx=32)
    checks['run_boost_bounded'] = 0 < o.railDynamics(2, 0, pace(moving))[0] - 2 <= 2.4
    moving.vx = -32
    checks['fresh_reversal_removes_assist'] = pace(moving) is None
    moving.vx = 0
    checks['fresh_stop_removes_assist'] = pace(moving) is None
    checks['stationary_slippery_not_powered'] = 23.9 < o.railDynamics(24, 0)[0] < 24 and o.railDynamics(0, 0)[0] == 0
    checks['all_grade_speeds_bounded'] = all(0 <= o.railDynamics(s, g, 48)[0] <= 48 for s in (0, 2, 24, 48) for g in (-1, -.7, 0, .7, 1))

    # Synthetic supported rail isolates controller math, not geometry discovery.
    world = lua.eval('''function()
      return {floor=function(self,x,y,z)return {x=x,y=0,z=z}end,
       support=function(self,p)return {x=p.x,y=0,z=p.z}end,
       segment=function()return true end,
       arc=function(self,a,b)return {a=a,b=b,duration=3}end,
       at=function(self,plan,k)return {x=plan.a.x+(plan.b.x-plan.a.x)*k,y=0,z=0}end}
    end''')()
    c = o.new(world, lua.eval('function()return .5 end'))
    entry_plan = lua.table_from(dict(a=point(-20), b=point(), duration=10))
    entry_ctx = lua.table_from(dict(player=point(100, vx=32)))
    result = c.railKeepsUp(c, point(-20, vx=2), rail, entry_ctx, entry_plan)
    checks['late_entry_rejected'] = result == (False, 'entry-outside-follow-window')
    entry_ctx.player.x = 40
    checks['near_entry_allowed'] = c.railKeepsUp(c, point(-20, vx=2), rail, entry_ctx, entry_plan) is True
    for speed in (8, 32):
        c = o.new(world, lua.eval('function()return .5 end'))
        p = point(vx=2)
        p.onGround = True
        m = point(100, vx=speed)
        ctx = lua.table_from(dict(player=m, frame=1, time=0, scene='test', instance=1, phys=1, area=1, terrain=1))
        plan = lua.table_from(dict(a=point(), b=point(), landing=point(), duration=18, contactEntry=True))
        eligible = c.railKeepsUp(c, p, rail, ctx, plan)
        checks[f'low_momentum_{speed}_admitted'] = eligible is True
        predicted_speed, progress, frames = 2, 0, 0
        while progress < 240 and frames < 60:
            predicted_speed, travel, _ = o.railDynamics(predicted_speed, 0, o.railPace(rail, point(progress), point(100 + speed * frames, vx=speed)))
            progress = min(240, progress + travel)
            frames += 1
        out = c.begin(c, plan, 'rail', p, ctx, rail)
        live = 1
        continuous = True
        while out is not None:
            continuous &= 0 <= out.position.x - p.x <= 48
            p.x, p.y, p.z = out.position.x, out.position.y, out.position.z
            if c.task.phase != 'grind':
                break
            ctx.frame += 1
            ctx.time += 1 / 30
            m.x += speed
            out = c.advance(c, p, ctx)
            live += 1
        checks[f'prediction_live_{speed}_match'] = live == frames and p.x == progress == 240
        checks[f'continuous_{speed}_movement'] = continuous and live <= 60
    # Current-state support and clearance still veto assisted motion.
    for refusal in ('floor', 'segment'):
        w = lua.table_from(dict(world.items()))
        w[refusal] = lua.eval('function()return nil end')
        c = o.new(w, lua.eval('function()return .5 end'))
        p = point(vx=2)
        ctx.player = point(100, vx=32)
        checks[refusal + '_refusal_preserved'] = c.begin(c, plan, 'rail', p, ctx, rail) is None and c.task is None
    print(json.dumps(dict(passed=all(checks.values()), checks=checks), indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
