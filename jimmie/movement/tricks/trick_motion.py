"""Trick batches for Jimmie (2026-11-10). Each trick is a named recipe: how far the board turns on each
axis, which foot flicks or scoops and which way, and how high each foot lifts. The body, the feet-on-deck
fitting and the export are the existing tool chain's (trick-recipes/recipe_motion.py, ollie_motion.py).

  python trick_motion.py --out <folder>      writes tricks_bank_fragment.lua, tricks.json and sheets/<trick>.png

Nothing in brain/, main/ or the tool-chain folders is written. Rider is goofy: right foot forward, toes at -Y.
Signs (from the existing kickflip and shuvits): roll -360 = kickflip direction, +360 = heelflip direction;
yaw +180 = backside shuvit direction, -180 = frontside; flick/scoop +1 = toward +Y (heel side), -1 = toe side.
"""
from pathlib import Path
import argparse, json, math, sys
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'ollie-candidate'))
sys.path.insert(0, str(HERE.parents[1] / 'original-skate-motion-20261107' / 'trick-recipes'))
import ollie_motion as om          # export helpers, rig, preview colours
import recipe_motion as recipe      # the kickflip/shuvit generator this extends

core, stock = om.core, om.stock
vec, rot, transform, apply, REST = core.vec, core.rot, core.transform, core.apply, core.REST
curve = recipe.curve
PREFIX = 'jimmie_tricks_v1_'

def R(name, label, roll=0, yaw=0, flick=0, scoop=0, flick_d=19, scoop_d=18, front=38, rear=31, wrap=0, seconds=.9,
      odds=70, weight=1, min_air=.5, spin_end=None, how='', pivot=(-24, -3, 9), wrap_up=16, side=0, rise=14, half=None,
      nollie=False, body_spin=0, style=None):
    return dict(id=name, label=label, roll_degrees=roll, yaw_degrees=yaw, front_flick_side=flick, rear_scoop_side=scoop,
                flick_distance=flick_d if flick else 0, scoop_distance=scoop_d if scoop else 0, front_lift=front, rear_lift=rear,
                wrap_degrees=wrap, wrap_pivot=pivot, wrap_up=wrap_up, wrap_side=side, rise=rise, half=half, nollie=nollie, body_spin=body_spin, style=style, seconds=seconds, odds=odds, weight=weight, min_air=min_air, spin_end=spin_end, how=how)

# Batch 1: flips and shuvits. "how" is the one-line description a skater would check the animation against.
BATCH1 = [
 R('bs_360_shuvit', 'backside 360 shuvit', yaw=360, scoop=-1, scoop_d=24, front=30, rear=33, odds=80,
   how='board spins a full turn flat, backside, under him; no flip'),
 R('fs_360_shuvit', 'frontside 360 shuvit', yaw=-360, scoop=1, scoop_d=26, front=31, rear=34, odds=85,
   how='board spins a full turn flat, frontside; no flip'),
 R('varial_kickflip', 'varial kickflip', roll=-360, yaw=180, flick=1, scoop=-1, odds=85,
   how='kickflip plus a backside pop shuvit: one flip, half a turn'),
 R('varial_heelflip', 'varial heelflip', roll=360, yaw=-180, flick=-1, scoop=1, flick_d=21, scoop_d=20, odds=90,
   how='heelflip plus a frontside pop shuvit: one flip, half a turn'),
 R('tre_flip', '360 flip', roll=-360, yaw=360, flick=1, scoop=-1, scoop_d=24, front=40, rear=34, odds=110, min_air=.55,
   how='kickflip plus a backside 360 shuvit'),
 R('hardflip', 'hardflip', roll=-180, wrap=-180, flick=1, scoop=1, front=44, rear=40, odds=110, pivot=(0, -3, 0), wrap_up=24, rise=0, half=-1,
   how='the board comes up on end between his legs, turning over as it goes, and lands turned half way'),
 R('inward_heelflip', 'inward heelflip', roll=360, yaw=180, flick=-1, scoop=-1, flick_d=21, odds=110,
   how='heelflip plus a backside pop shuvit'),
 R('laser_flip', 'laser flip', roll=360, yaw=-360, flick=-1, scoop=1, flick_d=21, scoop_d=26, front=40, rear=34, odds=130, min_air=.55,
   how='heelflip plus a frontside 360 shuvit'),
 R('double_kickflip', 'double kickflip', roll=-720, flick=1, flick_d=22, front=42, rear=34, odds=100, min_air=.55, spin_end=.68,
   how='two full kickflip rotations before he catches it'),
 R('impossible', 'impossible', wrap=-360, scoop=-1, scoop_d=6, front=44, rear=16, odds=120, min_air=.55, spin_end=.68, side=-17, rise=0,
   how='board wraps end over end around his back foot; no sideways flip'),
]
EXISTING = [   # already in the bank: give them names, odds and weights
 dict(id='trick', label='ollie', odds=20, weight=4), dict(id='kickflip', label='kickflip', odds=70, weight=3),
 dict(id='heelflip', label='heelflip', odds=70, weight=2), dict(id='bs_pop_shuvit', label='backside pop shuvit', odds=45, weight=2),
 dict(id='fs_pop_shuvit', label='frontside pop shuvit', odds=45, weight=2),
]

def G(name, label, hand=None, at=None, how='', odds=60, weight=1, spin=0, tuck=14, bend=16, roll=0, pitch=0, twist=0, lean=0, shift=0,
      feet_off=None, hip=0, seconds=22 / 30, min_air=.55, base='ollie', ground=False, nollie=False, plant=None, hold=None, style=None, windup=False):
    """An ollie with something added: a grab (hand + the spot on the board it holds), a tweak, feet off, or a body spin."""
    return dict(id=name, label=label, hand=hand, at=at, how=how, odds=odds, weight=weight, spin=spin, tuck=tuck, bend=bend, roll=roll,
                pitch=pitch, twist=twist, lean=lean, shift=shift, feet_off=feet_off, hip=hip, seconds=seconds, min_air=min_air,
                air=True, yaw_degrees=0, wrap_degrees=0, half=None, base=base, ground=ground, nollie=nollie, plant=plant, hold=hold, style=style, windup=windup, body_spin=0)

# Batch 2: grabs and spins. He is goofy: the right hand is the front hand, toes point to -Y, heels to +Y.
# "at" is the spot on the board the hand holds: x along the deck (+ nose), y across it (- toe edge, + heel edge).
BATCH2 = [
 G('melon', 'melon grab', hand='right', at=(6, 11, -1), roll=14, lean=10, twist=-14, bend=10, tuck=22, hip=-6,
   how='front hand holds the heel edge between his feet'),
 G('indy', 'indy grab', hand='left', at=(-4, -12, -1), roll=-16, bend=30, tuck=22, hip=-6,
   how='back hand holds the toe edge between his feet'),
 G('mute', 'mute grab', hand='right', at=(8, -12, -1), roll=-16, bend=30, twist=16, tuck=22, hip=-6,
   how='front hand holds the toe edge between his feet'),
 G('stalefish', 'stalefish', hand='left', at=(-8, 11, -1), roll=14, lean=-10, twist=18, bend=8, tuck=22, hip=-6, odds=75,
   how='back hand reaches behind his back leg to the heel edge'),
 G('nosegrab', 'nosegrab', hand='right', at=(38, -3, 2), pitch=-16, lean=22, bend=18, tuck=20, hip=-4,
   how='front hand holds the nose, nose pulled up'),
 G('tailgrab', 'tailgrab', hand='left', at=(-38, -3, 2), pitch=16, lean=-22, bend=18, tuck=20, hip=-4,
   how='back hand holds the tail, tail pulled up'),
 G('method', 'method air', hand='right', at=(6, 11, -1), roll=58, shift=14, lean=6, twist=-20, bend=-14, tuck=26, hip=-2, odds=85,
   how='front hand on the heel edge, board pulled up behind him, back arched'),
 G('airwalk', 'airwalk', hand='right', at=(38, -3, 2), pitch=-10, lean=20, bend=14, tuck=10, feet_off=dict(right=(0, -26, 12), left=(0, 24, 14)), odds=95,
   how='front hand holds the nose while both feet leave the board and scissor apart'),
 G('bs_180', 'backside 180', spin=180, odds=55, weight=2, how='he and the board turn half way round together, backside, and he lands rolling backwards'),
 G('fs_180', 'frontside 180', spin=-180, odds=55, weight=2, how='he and the board turn half way round together, frontside, and he lands rolling backwards'),
 G('bs_360', 'backside 360', spin=360, odds=110, how='he and the board turn a full turn together, backside'),
 G('fs_360', 'frontside 360', spin=-360, odds=110, how='he and the board turn a full turn together, frontside'),
]

# Batch 3: named grinds and slides. On a visible rail the game sits him so that a line through the board's truck
# undersides lies on the rail top. In the rig that line is y=-3, z=-9.5. Each grind names the point of the board
# that touches the rail ("on") and how the board is turned about that point, so the contact stays on the line.
RAIL_Y, RAIL_Z = -3., -9.5
# The deck, nose and tail heights were set by measuring (capture-tools/railcheck.py) so nothing sinks into the rail.
REAR_TRUCK, FRONT_TRUCK, DECK, NOSE, TAIL = (-37, -3, -9.5), (37, -3, -9.5), (0, -3, -1.7), (54, -3, -.7), (-54, -3, -.7)
def S(name, label, on, pitch=0, yaw=0, hip=0, crouch=8, how='', weight=1):
    return dict(id=name, label=label, on=on, pitch=pitch, yaw=yaw, hip=hip, crouch=crouch, how=how, weight=weight, seconds=1 / 3,
                grind=True, yaw_degrees=0, wrap_degrees=0, half=None, odds=40, min_air=0)
BATCH3 = [
 S('grind_5_0', '5-0 grind', REAR_TRUCK, pitch=-16, hip=-9, how='back truck on the rail, nose in the air'),
 S('grind_nose', 'nosegrind', FRONT_TRUCK, pitch=16, hip=9, how='front truck on the rail, tail in the air'),
 S('grind_crooked', 'crooked grind', FRONT_TRUCK, pitch=14, yaw=16, hip=8, how='front truck on the rail, tail up and swung out to one side'),
 S('grind_smith', 'smith grind', REAR_TRUCK, pitch=7, yaw=-26, hip=-5, how='back truck on the rail, nose dipped below it on his toe side'),
 S('grind_feeble', 'feeble grind', REAR_TRUCK, pitch=7, yaw=26, hip=-5, how='back truck on the rail, nose dipped below it on the far side'),
 S('slide_board', 'boardslide', DECK, yaw=90, crouch=10, weight=2, how='board across the rail, sliding on the middle of the deck'),
 S('slide_lip', 'lipslide', DECK, yaw=-90, crouch=10, how='board across the rail the other way round, sliding on the middle of the deck'),
 S('slide_nose', 'noseslide', NOSE, yaw=90, crouch=9, how='board across the rail, sliding on the nose'),
 S('slide_tail', 'tailslide', TAIL, yaw=90, crouch=9, how='board across the rail, sliding on the tail'),
 S('slide_blunt', 'bluntslide', (-54, -3, -2.2), yaw=90, pitch=-50, crouch=6, how='tail on the rail with the board standing up steeply above it'),
]
# Batch 4: manuals. Ground poses: the board tips about the wheels that stay on the floor.
REAR_WHEELS, FRONT_WHEELS = (-37, -3, -14.5), (37, -3, -14.5)
def MAN(name, label, on, pitch, hip, how, foot_off=None):
    d = S(name, label, on, pitch=pitch, hip=hip, crouch=5, how=how); d.update(grind=True, manual=True, floor=True, foot_off=foot_off); return d
BATCH4 = [
 MAN('manual', 'manual', REAR_WHEELS, -15, -10, 'rolling on the back wheels only, nose in the air'),
 MAN('nose_manual', 'nose manual', FRONT_WHEELS, 15, 10, 'rolling on the front wheels only, tail in the air'),
 MAN('one_foot_manual', 'one-foot manual', REAR_WHEELS, -15, -12, 'a manual with his front foot lifted off the board', foot_off=dict(right=(6, -14, 16))),
]
# Batch 5: stance and old-school. A "style" trick has its own ground wind-up, chosen before he leaves the ground.
STEP_OFF, STEP_ON = [(0, 0), (.55, 1), (1, 1)], [(0, 1), (.12, 1), (.5, 0), (1, 0)]
BATCH5 = [
 G('windup_nollie', 'wind-up for a nollie', base='windup', ground=True, nollie=True, windup=True, tuck=0, bend=0, seconds=.2),
 G('windup_boneless', 'wind-up for a boneless', base='windup', ground=True, windup=True, hand='left', at=(-4, -12, -1), hold=[(0, 0), (.6, 1), (1, 1)],
   plant=STEP_OFF, tuck=0, bend=16, seconds=.2),
 G('windup_nocomply', 'wind-up for a no-comply', base='windup', ground=True, windup=True, plant=STEP_OFF, hold=[(0, 0), (1, 0)], tuck=0, bend=0, seconds=.2),
 G('nollie', 'nollie', nollie=True, style='nollie', tuck=0, bend=0, odds=45, weight=2, how='he pops off the nose with his front foot and the tail comes up after it'),
 R('nollie_kickflip', 'nollie kickflip', roll=-360, flick=1, nollie=True, style='nollie', odds=95, how='popped off the nose; the back foot flicks the kickflip'),
 R('nollie_heelflip', 'nollie heelflip', roll=360, flick=-1, flick_d=21, nollie=True, style='nollie', odds=95, how='popped off the nose; the back foot flicks the heelflip'),
 G('boneless', 'boneless', style='boneless', hand='left', at=(-4, -12, -1), hold=[(0, 1), (.55, 1), (.8, 0), (1, 0)], plant=STEP_ON, roll=-10, bend=22, tuck=18, hip=-4, odds=70,
   how='front foot steps off to the ground, back hand holds the board, he jumps off that foot and puts it back on'),
 G('no_comply', 'no-comply', style='nocomply', plant=STEP_ON, hold=[(0, 0), (1, 0)], tuck=10, bend=6, odds=70,
   how='front foot steps off to the ground while the back foot pops the board up, then he jumps back on'),
 R('bigspin', 'bigspin', yaw=360, scoop=-1, scoop_d=24, front=30, rear=33, body_spin=180, odds=100, min_air=.55,
   how='the board does a backside 360 shuvit while he turns half way with it, and he lands rolling backwards'),
 R('fs_bigspin', 'frontside bigspin', yaw=-360, scoop=1, scoop_d=26, front=31, rear=34, body_spin=-180, odds=105, min_air=.55,
   how='the board does a frontside 360 shuvit while he turns half way with it, and he lands rolling backwards'),
 R('double_heelflip', 'double heelflip', roll=720, flick=-1, flick_d=22, front=42, rear=34, odds=105, min_air=.55, spin_end=.68,
   how='two full heelflip rotations before he catches it'),
 G('ollie_north', 'ollie north', feet_off=dict(right=(20, -2, 6), left=(0, 0, 0)), tuck=6, bend=6, odds=55, how='an ollie with his front foot kicked forward off the nose'),
]
GRIND_NAMES = dict(balance042='50-50 grind', balance038='5-0 grind', balance039='nosegrind')
TRICKS = {r['id']: r for r in BATCH1 + BATCH2 + BATCH3 + BATCH4 + BATCH5}
FRAMES = {n: round(r['seconds'] * 30) for n, r in TRICKS.items()}


class Study(recipe.Study):
    """recipe_motion's pose with two additions: an end-over-end wrap about the back foot, and a per-trick spin window."""
    def pose(self, clip, t):
        if clip not in TRICKS: return super().pose(clip, t)
        if TRICKS[clip].get('air'): return self.pose_air(clip, t)
        if TRICKS[clip].get('grind'): return self.pose_grind(clip, t)
        r = TRICKS[clip]; a = dict(recipe.ANCHORS)
        if r['spin_end']: a['spin_end'] = r['spin_end']; a['front_catch'] = max(a['front_catch'], r['spin_end'] + .06)
        _, mats, _ = core.Study.pose(self, 'trick', t)
        mats = {n: m.copy() for n, m in mats.items()}
        spin = curve([(0, 0), (a['release'], 0), (a['spin_end'], 1), (1, 1)], t)
        # Linear through the middle so the board turns at a steady rate instead of easing in and out.
        mid = (t - a['release']) / (a['spin_end'] - a['release'])
        if 0 < mid < 1: spin = .5 * spin + .5 * mid
        roll = r['roll_degrees'] * spin; yaw = r['yaw_degrees'] * spin; wrap = r['wrap_degrees'] * spin
        pitch = curve([(0, 0), (.11, 0), (.21, -21), (.35, 0), (1, 0)], t) * (-1 if r['nollie'] else 1)   # nollie: the nose snaps down instead of the tail
        flicker = 'left' if r['nollie'] else 'right'                                                       # nollie: the back foot does the flick
        lift = max(0., 37 * abs(math.sin(math.radians(pitch)))) + curve([(0, 0), (.25, 0), (.45, 5), (.65, 3), (.82, 0), (1, 0)], t)
        lift += r['rise'] * math.sin(math.pi * spin)
        center = vec([0, -3, 0])
        boardR = rot([0, 0, 1], yaw) @ rot([0, 1, 0], pitch) @ rot([1, 0, 0], roll)
        boardM = transform(boardR, center, center + vec([0, 0, lift]))
        if r['wrap_degrees']:
            # Turn end over end about a point just above the tail, where the back foot is.
            # "side" moves it toward his toes on the way round, so it passes in front of the shin instead of through it.
            pivot = vec(r['wrap_pivot']); swing = math.sin(math.pi * spin)
            boardM = transform(rot([0, 1, 0], wrap), pivot, pivot + vec([0, r['wrap_side'] * swing, r['wrap_up'] * swing])) @ boardM
        for n in core.BOARD_PARTS: mats[n] = boardM.copy()
        deck = apply(boardM, self.v)[self.deck]; contact = {}
        flick = curve([(0, 0), (.17, 0), (.27, 1), (.38, 1), (.60, 0), (1, 0)], t)
        for side, x, footyaw in [('left', -25., -8.), ('right', 25., 48.)]:
            catch = a['front_catch'] if side == 'right' else a['rear_catch']
            w = curve([(0, 0), (.17, 0), (a['release'], 1), ((max(.76, a['spin_end'] + .08) if side == 'left' else a['spin_end']), 1), (catch, 0), (1, 0)], t)
            Rf = rot([0, 1, 0], pitch) @ rot([0, 0, 1], footyaw)
            target = apply(transform(rot([0, 1, 0], pitch), center, center + vec([0, 0, lift])), [[x, -3, 10]])[0]
            attached = transform(Rf, REST[side + '_foot'][0], target)
            if w < 1:
                gap, area = core.triangle_clearance(apply(attached, self.v)[self.soles[side]], deck)
                if math.isfinite(gap) and area >= 80: attached[2, 3] -= gap
                elif w == 0: raise ValueError(f'{clip} {t:.2f}: {side} foot is not over the deck at the catch')
            if side == flicker:
                lateral = r['front_flick_side'] * r['flick_distance'] * flick; toe = r['front_flick_side'] * 32 * flick; reach = 7 * flick
            else:
                lateral = r['rear_scoop_side'] * r['scoop_distance'] * flick; toe = -r['rear_scoop_side'] * 12 * flick; reach = -11 * flick
            high = r['front_lift'] if side == 'right' else r['rear_lift']
            free_target = vec([x + reach, -3 + lateral, 10 + high + self.base_lift[side]])
            free_yaw = footyaw + (r['rear_scoop_side'] * 26 * flick if side != flicker else -r['front_flick_side'] * 12 * flick)
            free = transform(rot([1, 0, 0], toe) @ rot([0, 0, 1], free_yaw), REST[side + '_foot'][0], free_target)
            M = recipe.rigid_mix(attached, free, w, REST[side + '_foot'][0])
            if 0 < w < 1:
                gap, area = core.triangle_clearance(apply(M, self.v)[self.soles[side]], deck)
                if math.isfinite(gap) and area > 1e-6: M[2, 3] += max(0., -gap)
            mats[side + '_foot'] = M
            if w == 0: contact[side] = {'kind': 'deck'}
            upper, lower = side + '_upper_leg', side + '_lower_leg'; p, k = REST[upper]; _, ank = REST[lower]
            hip = apply(mats['hips'], [p])[0]; ankle = apply(M, [ank])[0]
            knee = core.two_link(hip, ankle, np.linalg.norm(k - p), np.linalg.norm(ank - k), [0, -1, 0])
            mats[upper] = transform(core.align(k - p, knee - hip), p, hip)
            mats[lower] = transform(core.align(ank - k, ankle - knee), k, knee)
        # Shoulders open with the flick and wind against the scoop, as the existing recipes do.
        turn = -r['front_flick_side'] * 8 * flick + r['rear_scoop_side'] * 6 * flick * (1 if r['yaw_degrees'] else 0)
        chest = apply(mats['torso'], [REST['torso'][0]])[0]
        twist = transform(rot([0, 0, 1], turn), chest, chest)
        for bone in ('torso', 'head', 'left_upper_arm', 'left_lower_arm', 'left_hand', 'right_upper_arm', 'right_lower_arm', 'right_hand'):
            mats[bone] = twist @ mats[bone]
        if r['body_spin']:
            # Bigspin: he turns half way while the board turns all the way. Finished before the catch.
            k = min(1., max(0., (t - .2) / .58)); Sb = transform(rot([0, 0, 1], r['body_spin'] * core.smooth(k)), center, center)
            mats = {n: (m if n in core.BOARD_PARTS else Sb @ m) for n, m in mats.items()}
        return core.deform(self.d, self.weights, mats), mats, {'support': contact, 'roll': roll, 'yaw': yaw, 'wrap': wrap}


    def pose_air(self, clip, t):
        """The ollie's own curves, plus a grab, tweak, feet-off or whole-body spin that fades in and out around the peak."""
        g = TRICKS[clip]; c = {k: om.curve(v, t) for k, v in om.CURVES[g['base']].items()}
        if g['nollie']: c['pitch'] = -c['pitch']; c['front'], c['rear'] = -c['rear'], -c['front']     # mirrored end for end
        w = curve(g['hold'] or [(0, 0), (.16, 0), (.38, 1), (.62, 1), (.84, 0), (1, 0)], t)
        pitch = c['pitch'] + g['pitch'] * w
        lift = c['lift'] + g['tuck'] * w + max(0., 37 * abs(math.sin(math.radians(c['pitch']))))
        center = vec([0, -3, 0])
        boardR = rot([0, 1, 0], pitch) @ rot([1, 0, 0], g['roll'] * w)
        boardM = transform(boardR, center, center + vec([0, g['shift'] * w, lift]))
        if g['ground']: boardM[2, 3] += self.floor - float(apply(boardM, self.v[self.board])[:, 2].min())   # wheels stay on the floor
        mats = {n: boardM.copy() for n in core.BOARD_PARTS}
        deck = apply(boardM, self.v)[self.deck]; contact = {}
        for side, x, yaw in [('left', c['rear'], -8.), ('right', c['front'], 48.)]:
            target = apply(boardM, [[x, -3, 10]])[0]
            M = transform(boardR @ rot([0, 0, 1], yaw), REST[side + '_foot'][0], target)
            M[2, 3] += self.base_lift[side]
            gap, area = core.triangle_clearance(apply(M, self.v)[self.soles[side]], deck)
            if math.isfinite(gap) and area >= 80: M[2, 3] -= gap; contact[side] = {'kind': 'deck'}
            elif not g['roll']: raise ValueError(f'{clip} {t:.2f}: {side} foot off the deck')
            if g['feet_off']:
                free = transform(rot([0, 0, 1], yaw), REST[side + '_foot'][0], target + vec(g['feet_off'][side]))
                M = recipe.rigid_mix(M, free, w, REST[side + '_foot'][0])
            if g['plant'] and side == 'right':
                # Front foot off the board on his toe side: on the floor during the wind-up, trailing below as he leaves it.
                wp = curve(g['plant'], t)
                spot = vec([x - 4, -29, self.floor + 10]) if g['ground'] else target + vec([-4, -24, -22])
                M = recipe.rigid_mix(M, transform(rot([0, 0, 1], yaw), REST[side + '_foot'][0], spot), wp, REST[side + '_foot'][0])
            mats[side + '_foot'] = M
        bend = c['bend'] + g['bend'] * w
        hip = vec([0., 1. + .12 * bend, 48. + c['hip'] + g['hip'] * w])
        lean = rot([0, 1, 0], 5. + g['lean'] * w)
        mats['hips'] = transform(lean @ rot([1, 0, 0], .35 * bend), REST['hips'][0], hip)
        chest = apply(mats['hips'], [REST['torso'][0]])[0]
        torsoR = rot([0, 0, 1], g['twist'] * w) @ lean @ rot([1, 0, 0], bend)
        mats['torso'] = transform(torsoR, REST['torso'][0], chest)
        neck = apply(mats['torso'], [REST['head'][0]])[0]
        mats['head'] = transform(rot([0, 0, 1], g['twist'] * w * .5) @ lean @ rot([1, 0, 0], .35 * bend) @ rot([0, 0, 1], 24.), REST['head'][0], neck)
        miss = 0.
        for side, s in [('left', -1), ('right', 1)]:
            upper, lower = side + '_upper_leg', side + '_lower_leg'
            a, b = REST[upper]; _, e = REST[lower]
            hipjoint = apply(mats['hips'], [a])[0]; ankle = apply(mats[side + '_foot'], [e])[0]
            l1, l2 = np.linalg.norm(b - a), np.linalg.norm(e - b); d = np.linalg.norm(ankle - hipjoint)
            if d > l1 + l2 - .01 or d < abs(l1 - l2) + .01:      # leg cannot reach: move the foot along the line to where it can
                ankle = hipjoint + (ankle - hipjoint) * (min(l1 + l2 - .02, max(abs(l1 - l2) + .02, d)) / d)
                mats[side + '_foot'][:3, 3] += ankle - apply(mats[side + '_foot'], [e])[0]
            knee = core.two_link(hipjoint, ankle, l1, l2, [0, -1, 0])
            mats[upper] = transform(core.align(b - a, knee - hipjoint), a, hipjoint)
            mats[lower] = transform(core.align(e - b, ankle - knee), b, knee)
            ua, la, hand = side + '_upper_arm', side + '_lower_arm', side + '_hand'
            a, b = REST[ua]; _, e = REST[la]
            shoulder = apply(mats['torso'], [a])[0]
            Ra = torsoR @ rot([0, 1, 0], s * (18 - c['arm'] * .9)) @ rot([1, 0, 0], -10 + c['arm'] * .2 - c['swing'])
            elbow = shoulder + Ra @ (b - a)
            Rb = Ra @ rot([1, 0, 0], -15 - s * c['arm'] * .4)
            wrist = elbow + Rb @ (e - b)
            if g['hand'] == side and w > 0:
                l1, l2 = np.linalg.norm(b - a), np.linalg.norm(e - b)
                goal = apply(boardM, [vec(g['at']) + vec([0, 0, 2])])[0]
                d = np.linalg.norm(goal - shoulder)
                if w >= .999: miss = max(0., d - (l1 + l2))
                want = (1 - w) * wrist + w * goal
                d = np.linalg.norm(want - shoulder)
                want = shoulder + (want - shoulder) * (min(l1 + l2 - .02, max(abs(l1 - l2) + .02, d)) / d)
                elbow = core.two_link(shoulder, want, l1, l2, [s, .6, .2])
                Ra = core.align(b - a, elbow - shoulder); Rb = core.align(e - b, want - elbow); wrist = want
            mats[ua] = transform(Ra, a, shoulder); mats[la] = transform(Rb, b, elbow)
            mats[hand] = transform(Rb, REST[hand][0], wrist)
        turned = 0.
        if g['spin']:
            # He and the board turn together. Finished before the catch, so the landing never cuts it short.
            k = min(1., max(0., (t - .04) / .78)); turned = g['spin'] * (.5 * k + .5 * core.smooth(k))
            S = transform(rot([0, 0, 1], turned), center, center)
            mats = {n: S @ m for n, m in mats.items()}
        return core.deform(self.d, self.weights, mats), mats, {'support': contact, 'roll': 0., 'yaw': turned, 'wrap': 0., 'miss': miss}

    def pose_grind(self, clip, t):
        """Settle from the riding stance into the grind over the first two thirds of the clip; the game holds the last frame."""
        g = TRICKS[clip]; e = core.smooth(min(1., t / .68))
        on = vec(g['on']); boardR = rot([0, 0, 1], g['yaw'] * e) @ rot([0, 1, 0], g['pitch'] * e)
        # Start as the 50-50 (wheels level, trucks on the line) and end with the named contact point on the line.
        start = transform(np.eye(3), vec([0, 0, 0]), vec([0, 0, 0]))
        end = transform(boardR, on, vec([on[0] if abs(g['yaw']) < 45 else 0., RAIL_Y, on[2] if g.get('floor') else RAIL_Z]))
        boardM = transform(boardR, on, (1 - e) * apply(start, [on])[0] + e * apply(end, [on])[0])
        mats = {n: boardM.copy() for n in core.BOARD_PARTS}
        deck = apply(boardM, self.v)[self.deck]; contact = {}
        turn = g['yaw'] * e
        for side, x, yaw in [('left', -25., -8.), ('right', 25., 48.)]:
            target = apply(boardM, [[x, -3, 10]])[0]
            M = transform(boardR @ rot([0, 0, 1], yaw), REST[side + '_foot'][0], target)
            M[2, 3] += self.base_lift[side]
            gap, area = core.triangle_clearance(apply(M, self.v)[self.soles[side]], deck)
            if math.isfinite(gap) and area >= 60: M[2, 3] -= gap; contact[side] = {'kind': 'deck'}
            if g.get('foot_off') and side in g['foot_off']:
                free = transform(rot([0, 0, 1], yaw), REST[side + '_foot'][0], target + vec(g['foot_off'][side]))
                M = recipe.rigid_mix(M, free, e, REST[side + '_foot'][0])
            mats[side + '_foot'] = M
        mid = apply(boardM, [[g['hip'] * e, -3, 0]])[0]
        bodyR = rot([0, 0, 1], turn * .6)                      # hips follow the board most of the way, shoulders less
        hip = vec([mid[0], mid[1] + 4., mid[2] + 48. - g['crouch'] * e])
        lean = rot([0, 1, 0], 5. - .5 * g['hip'] * e)
        mats['hips'] = transform(bodyR @ lean @ rot([1, 0, 0], 6 * e), REST['hips'][0], hip)
        chest = apply(mats['hips'], [REST['torso'][0]])[0]
        torsoR = rot([0, 0, 1], turn * .35) @ lean @ rot([1, 0, 0], 14 * e)
        mats['torso'] = transform(torsoR, REST['torso'][0], chest)
        neck = apply(mats['torso'], [REST['head'][0]])[0]
        mats['head'] = transform(rot([0, 0, 1], turn * .2) @ lean @ rot([1, 0, 0], 5 * e) @ rot([0, 0, 1], 24.), REST['head'][0], neck)
        for side, s in [('left', -1), ('right', 1)]:
            upper, lower = side + '_upper_leg', side + '_lower_leg'
            a, b = REST[upper]; _, k = REST[lower]
            hipjoint = apply(mats['hips'], [a])[0]; ankle = apply(mats[side + '_foot'], [k])[0]
            l1, l2 = np.linalg.norm(b - a), np.linalg.norm(k - b); d = np.linalg.norm(ankle - hipjoint)
            if d > l1 + l2 - .01 or d < abs(l1 - l2) + .01:
                ankle = hipjoint + (ankle - hipjoint) * (min(l1 + l2 - .02, max(abs(l1 - l2) + .02, d)) / d)
                mats[side + '_foot'][:3, 3] += ankle - apply(mats[side + '_foot'], [k])[0]
            knee = core.two_link(hipjoint, ankle, l1, l2, bodyR @ vec([0, -1, 0]))
            mats[upper] = transform(core.align(b - a, knee - hipjoint), a, hipjoint)
            mats[lower] = transform(core.align(k - b, ankle - knee), b, knee)
            ua, la, hand = side + '_upper_arm', side + '_lower_arm', side + '_hand'
            a, b = REST[ua]; _, k = REST[la]
            shoulder = apply(mats['torso'], [a])[0]; arm = 44 * e
            Ra = torsoR @ rot([0, 1, 0], s * (18 - arm * .9)) @ rot([1, 0, 0], -10 + arm * .2)
            elbow = shoulder + Ra @ (b - a); Rb = Ra @ rot([1, 0, 0], -15 - s * arm * .4); wrist = elbow + Rb @ (k - b)
            mats[ua] = transform(Ra, a, shoulder); mats[la] = transform(Rb, b, elbow); mats[hand] = transform(Rb, REST[hand][0], wrist)
        # Same convention as the existing grind poses: the clip is lifted so the wheels' rest floor is at zero.
        return core.deform(self.d, self.weights, mats), mats, {'support': contact, 'roll': 0., 'yaw': turn, 'wrap': 0.}

def export(study):
    """Same channel layout and backwards-deck maths as ollie_motion.export."""
    out = {}
    for clip, n in FRAMES.items():
        poses = [study.pose(clip, k / (n - 1)) for k in range(n)]; roles = {}
        for role, bones in [('body', stock.BODY), ('board', stock.BOARD)]:
            channels = [[] for _ in range(3 + 3 * len(bones))]; previous = {}
            for _, matrices, _ in poses:
                pos, rots = stock.channels_for(matrices, bones); row = pos[:]
                for bone in bones:
                    q = stock.euler_xyz(rots[bone], previous.get(bone)); previous[bone] = q
                    row.extend(int(round(float(x) * 32768 / math.pi)) for x in q)
                for dest, v in zip(channels, row): dest.append(v)
            values, index = stock.compact(channels)
            roles[role] = {'name': f'{PREFIX}{role}_{clip}', 'flags': 5, 'values': values, 'index': index}
        board = roles['board']; ch = []
        for count, off in zip(board['index'][::2], board['index'][1::2]):
            v = board['values'][off:off + count]; ch.append([(v[min(k, count - 1)] + 32768) % 65536 - 32768 for k in range(n)])
        prev = None; r3 = [[], [], []]
        for k in range(n):
            Rm = stock.rotation_xyz([ch[i][k] * math.pi / 32768 for i in range(3, 6)]) @ np.diag([-1, 1, -1])
            e = stock.euler_xyz(Rm, prev); prev = e
            for dest, v in zip(r3, e): dest.append(round(float(v) * 32768 / math.pi))
        values, index = stock.compact(ch[:3] + r3)
        roles['boardReverse'] = {'name': f'{PREFIX}board_reverse_{clip}', 'flags': 5, 'values': values, 'index': index}
        out[clip] = {'frames': n, 'duration': n / 30, **roles}
    return out


def landing_for(r):
    if r['half']: return 'land_bs_pop_shuvit' if r['half'] > 0 else 'land_fs_pop_shuvit'
    half = (abs(r['yaw_degrees']) // 180) % 2 == 1
    if not half: return 'land_ollie'
    return 'land_bs_pop_shuvit' if r['yaw_degrees'] > 0 else 'land_fs_pop_shuvit'


def bank_lines(clips, five=False):
    ids5 = {r['id'] for r in BATCH5}
    clips = {k: v for k, v in clips.items() if (k in ids5) == five}
    lines = ['-- Trick batch 5 (2026-11-10): nollies, boneless, no-comply, bigspins, double heelflip, ollie north, and their wind-ups.' if five else
             '-- Trick batches 1 to 4 (2026-11-10): flips, shuvits, grabs, spins, grinds, slides and manuals, plus real names, odds and pick weights.']
    for clip, q in clips.items():
        r = TRICKS[clip]
        for role in ('body', 'board', 'boardReverse'):
            a = q[role]
            lines.append('smlua_anim_util_register_animation(%s,%d,0,0,0,%d,%s,%s)' % (json.dumps(a['name']), a['flags'], q['frames'], stock.table(a['values']), stock.table(a['index'])))
        if r.get('grind') or r.get('windup'):
            lines.append('M.clips["%s"]={frames=%d,duration=%r,loop=false,turn=0,catch=0.84,body="%s",board="%s",boardReverse="%s",landing=nil,name="%s"}' % (
                clip, q['frames'], q['duration'], q['body']['name'], q['board']['name'], q['boardReverse']['name'], r['label']))
            continue
        lines.append('M.clips["%s"]={frames=%d,duration=%r,loop=false,turn=%d,catch=%s,pop=%s,body="%s",board="%s",boardReverse="%s",landing="%s",name="%s",odds=%d,weight=%d,minAir=%r%s}' % (
            clip, q['frames'], q['duration'], 1 if r['half'] else (abs(r['yaw_degrees']) // 180) % 2, '0.84' if r.get('air') else '0.86', '0' if r.get('air') else '0.15', q['body']['name'], q['board']['name'], q['boardReverse']['name'],
            landing_for(r), r['label'], r['odds'], r['weight'], r['min_air'],
            ((',spin=%d' % (1 if r['spin'] > 0 else -1)) if r.get('spin') and abs(r['spin']) == 180 else '')
            + ((',spin=%d' % (1 if r['body_spin'] > 0 else -1)) if r.get('body_spin') else '')
            + ((',style="%s"' % r['style']) if r.get('style') else '')))
    if five:
        lines.append('for _,n in ipairs({%s}) do M.trickList[#M.trickList+1]=n end' % ','.join('"%s"' % c for c in clips if not TRICKS[c].get('windup')))
        lines.append('M.styles=true')
        return lines
    for e in EXISTING:
        lines.append('if M.clips["%s"] then M.clips["%s"].name="%s";M.clips["%s"].odds=%d;M.clips["%s"].weight=%d end' % (e['id'], e['id'], e['label'], e['id'], e['odds'], e['id'], e['weight']))
    order = [e['id'] for e in EXISTING] + [c for c in clips if not TRICKS[c].get('grind') and not TRICKS[c].get('windup')]
    for clip, name in GRIND_NAMES.items(): lines.append('if M.clips["%s"] then M.clips["%s"].name="%s" end' % (clip, clip, name))
    grinds = [c for c in clips if TRICKS[c].get('grind') and not TRICKS[c].get('manual')]
    lines.append('M.manualList={%s}' % ','.join('"%s"' % c for c in clips if TRICKS[c].get('manual')))
    # Globals read by the rail code: which grinds may be used on a visible rail, and which board animations it may trust.
    lines.append('JIMMIE_GRINDS={{clip="balance042",weight=2},%s}' % ','.join('{clip="%s",weight=%d}' % (c, TRICKS[c]['weight']) for c in grinds))
    lines.append('JIMMIE_GRIND_CLIPS={};JIMMIE_GRIND_BOARDS={}')
    lines.append('for _,g in ipairs(JIMMIE_GRINDS) do local q=M.clips[g.clip];JIMMIE_GRIND_CLIPS[g.clip]=true;JIMMIE_GRIND_BOARDS[q.board]=true;JIMMIE_GRIND_BOARDS[q.boardReverse]=true end')
    lines.append('M.trickList={%s}' % ','.join('"%s"' % n for n in order))
    return lines


def sheet(study, clip, path, cols=9):
    """One labelled strip per trick, seen from behind and above so the board's turning axis is readable."""
    from PIL import Image, ImageDraw
    import actor_emit as emit
    d = study.d; faces = d['faces']; colors = emit.variant_colors(d, 'default')
    r = TRICKS[clip]; n = FRAMES[clip]; r.setdefault('how', '')
    picks = [round(k * (n - 1) / (2 * cols - 1)) for k in range(2 * cols)]
    V = rot([1, 0, 0], math.radians(28)) @ rot([0, 0, 1], math.radians(-40))
    cell, ch, sc = 210, 250, 1.15
    img = Image.new('RGB', (cols * cell, 2 * (ch + 20) + 60), (236, 236, 228)); dr = ImageDraw.Draw(img)
    dr.text((8, 4), f"{r['label'].upper()}   ({clip})", fill=(160, 30, 30))
    dr.text((8, 20), r['how'] + '.  (The game adds the real jump height.)', fill=(60, 60, 60))
    for i, k in enumerate(picks):
        t = k / (n - 1); pts, _, meta = study.pose(clip, t)
        rise = 0 if r.get('grind') or r.get('ground') else 55 * math.sin(math.pi * min(1, max(0, (t - .2) / .75)))
        p = pts @ V.T
        ox, oy = (i % cols) * cell + cell // 2, 60 + (i // cols) * (ch + 20) + ch - 30
        dr.line([(ox - cell // 2 + 8, oy), (ox + cell // 2 - 8, oy)], fill=(150, 150, 140), width=2)
        order = sorted(range(len(faces)), key=lambda f: -sum(p[j][1] for j in faces[f]))
        for f in order:
            a, b, c3 = (pts[j] for j in faces[f])
            nrm = np.cross(b - a, c3 - a); L = np.linalg.norm(nrm)
            shade = .72 + .28 * abs(float(nrm @ V[1]) / L) if L > 1e-9 else 1
            rgb = tuple(int(shade * sum(colors[j][q] for j in faces[f]) / 3) for q in range(3))
            dr.polygon([(ox + sc * p[j][0], oy - sc * (p[j][2] - study.floor) - rise) for j in faces[f]], fill=rgb)
        dr.text((ox - cell // 2 + 8, oy + 6), 'f%d  flip %d  turn %d%s' % (k, round(abs(meta['roll'])), round(abs(meta['yaw'])), ('  wrap %d' % round(abs(meta['wrap']))) if r['wrap_degrees'] else ''), fill=(40, 40, 40))
        if meta.get('miss', 0) > .5: dr.text((ox - cell // 2 + 8, oy + 18), 'hand short by %d' % round(meta['miss']), fill=(170, 30, 30))
    img.save(path)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=Path, required=True); ap.add_argument('--no-sheets', action='store_true'); ap.add_argument('--only', default='')
    a = ap.parse_args(); (a.out / 'sheets').mkdir(parents=True, exist_ok=True)
    study = Study(json.loads((HERE.parents[1] / 'original-skate-motion-20261107' / 'core-set' / 'rest_appearance.json').read_text()))
    clips = export(study)
    (a.out / 'tricks_bank_fragment.lua').write_text('\n'.join(bank_lines(clips)) + '\n', encoding='utf-8', newline='\n')
    (a.out / 'tricks5_bank_fragment.lua').write_text('\n'.join(bank_lines(clips, True)) + '\n', encoding='utf-8', newline='\n')
    (a.out / 'tricks.json').write_text(json.dumps([{k: r[k] for k in ('id', 'label', 'how', 'odds')} for r in EXISTING_AND_NEW()], indent=1) + '\n', encoding='utf-8')
    only = set(a.only.split(',')) if a.only else None
    if not a.no_sheets:
        for clip in clips:
            if not only or clip in only: sheet(study, clip, a.out / 'sheets' / f'{clip}.png')
    for clip in clips:
        if TRICKS[clip].get('hand'):
            print(f"  {clip}: hand short of the board by {study.pose(clip, .5)[2]['miss']:.1f}")
    print('Built', len(clips), 'tricks ->', a.out)

def EXISTING_AND_NEW():
    return [dict(how='', **e) for e in EXISTING] + BATCH1 + BATCH2 + BATCH3 + BATCH4 + [r for r in BATCH5 if not r.get('windup')]

if __name__ == '__main__': main()
