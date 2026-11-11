"""Verify private native raised-rail routes without conflating gfx state and rendering.

Consumes an existing guarded run only. No launch, installation, model manipulation
or network activity. Writes one receipt inside the supplied private run directory.
Use --self-test for in-memory parser/geometry regression tests without run data.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'tools/jimmie_harnesses/raised_rails.lua'
ROOMY_HARNESS = ROOT / 'tools/jimmie_harnesses/raised_rails_roomy.lua'
RUNTIME = (
    'main.lua', 'skate_probes.lua', 'skate_opportunities.lua', 'skate_rail_index.lua',
    'skate_surface_rails.lua', 'skate_visible_rails.lua', 'original_motion_controller.lua',
    'trick_outcomes.lua', 'skate_rail_binding.lua', 'skate_rail_presentation.lua', 'original_clip_bank.lua',
)
CASES = {
    'castle_banister': {
        'level': 6, 'area': 1, 'visual_level': 'LEVEL_CASTLE', 'floor': 512,
        'band': (592, 626), 'visual': ((-2653, 614, -1043), (-2039, 614, -1044)),
    },
    'bob_lower_fence': {
        'level': 9, 'area': 1, 'visual_level': 'LEVEL_BOB', 'floor': 768,
        'band': (879, 923), 'visual': ((-1521, 891, 2034), (1288, 891, 3820)),
    },
}
ROOMY_CASES = {'castle_banister_roomy':copy.deepcopy(CASES['castle_banister']),
               'bob_lower_fence':copy.deepcopy(CASES['bob_lower_fence'])}
LIMITS = (
    'Hidden actual engine with synthetic native analog/jump input after one initial '
    'placement per map; normal 75/1000 post-trick crash lottery. No seeded contact '
    'or held actor/Mario state. Header/gfx snapshots are not rendered acceptance. '
    'A safe live-clearance handback is reported separately and never satisfies a '
    'completed grind. Not human-play, physical-controller, camera, audio, '
    'multiplayer, all-map or public-release acceptance.'
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(value):
    if not isinstance(value, dict):
        return None
    coords = tuple(value.get(k) for k in ('x', 'y', 'z'))
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) for v in coords):
        return None
    return coords


def separation(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def line_error(p, a, b):
    delta = tuple(y-x for x, y in zip(a, b))
    length2 = sum(v*v for v in delta)
    if length2 < 1:
        return math.inf, math.inf
    t = sum((x-y)*d for x, y, d in zip(p, a, delta))/length2
    q = tuple(x+t*d for x, d in zip(a, delta))
    return separation(p, q), t


def raised_contact(event, spec):
    rail = event.get('rail') or {}
    visual = rail.get('visual') or {}
    p, a, b = point(event.get('position')), point(rail.get('a')), point(rail.get('b'))
    va, vb = point(visual.get('a')), point(visual.get('b'))
    if not all((p, a, b, va, vb)):
        return False
    expected_a, expected_b = spec['visual']
    endpoints = ((separation(va, expected_a) <= 1 and separation(vb, expected_b) <= 1)
                 or (separation(vb, expected_a) <= 1 and separation(va, expected_b) <= 1))
    error, t = line_error(p, a, b)
    visual_error, visual_t = line_error(p, va, vb)
    low, high = spec['band']
    return (rail.get('shapeSource') == 'static-surface-edge'
            and visual.get('source') == 'verified-static-alpha'
            and visual.get('level') == spec['visual_level']
            and visual.get('area') == spec['area'] and endpoints
            and all(low <= q[1] <= high for q in (p, a, b))
            and p[1]-spec['floor'] >= 75
            and error <= 12 and -.05 <= t <= 1.05
            and visual_error <= 32 and 0 <= visual_t <= 1)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def f32(value):
    return struct.unpack('f', struct.pack('f', value))[0]


def vector_close(a, b, tolerance=1e-6):
    return a is not None and b is not None and all(abs(x-y) <= tolerance for x, y in zip(a, b))


def truck_residual(gfx, native, visual):
    """Independent reconstruction, using the same quantized native angle indices."""
    a, b = point(visual.get('a')), point(visual.get('b'))
    if gfx is None or not a or not b or not isinstance(native, dict):
        return math.inf
    if not all(finite(native.get(k)) and native[k] == int(native[k]) for k in ('yaw','pitch','roll')):
        return math.inf
    if native['pitch'] % 65536 != 0:
        return math.inf
    yaw = math.floor((native['yaw'] % 65536)/16)*2*math.pi/4096
    roll = math.floor((native['roll'] % 65536)/16)*2*math.pi/4096
    cy, sy, cr, sr = math.cos(yaw), math.sin(yaw), math.cos(roll), math.sin(roll)
    axis = (cy*cr, sr, -sy*cr)
    anchor = (-3.1*cy*sr-3.1*sy, 3.1*cr, 3.1*sy*sr-3.1*cy)
    center = tuple(x+y for x, y in zip(gfx, anchor))
    residual = []
    for direction in (-1,1):
        truck = tuple(x+direction*35.34*d for x,d in zip(center,axis))
        error, t = line_error(truck,a,b)
        residual.append(error if 0 <= t <= 1 else math.inf)
    return max(residual)


def angles_equal(a,b):
    return (isinstance(a,dict) and isinstance(b,dict)
            and all(finite(a.get(k)) and finite(b.get(k))
                    and a[k] == int(a[k]) and b[k] == int(b[k])
                    and a[k] % 65536 == b[k] % 65536 for k in ('yaw','pitch','roll')))


def valid_certificate(trace, spec):
    certificate = trace.get('certificate') or {}
    root, delta = point(certificate.get('physical')), point(certificate.get('certifiedDelta'))
    visual = certificate.get('visual') or {}
    native = certificate.get('native') or {}
    if not root or not delta or not raised_contact(trace,spec):
        return False
    expected_a, expected_b = spec['visual']
    va, vb = point(visual.get('a')), point(visual.get('b'))
    endpoints = ((vector_close(va,expected_a) and vector_close(vb,expected_b))
                 or (vector_close(vb,expected_a) and vector_close(va,expected_b)))
    shifted = tuple(x+d for x,d in zip(root,delta))
    residual = truck_residual(shifted,native,visual)
    recorded_residual = certificate.get('maxTruckResidual')
    return (trace.get('grind') is True and trace.get('phase') in ('grind','dismount','exit')
            and trace.get('kind') == 'rail' and trace.get('clip') == 'balance042'
            and certificate.get('certificateFrame') == trace.get('frame')
            and certificate.get('method') == 'finite-native-shifted-envelope'
            and certificate.get('radius') == 116 and certificate.get('top') == 360
            and finite(certificate.get('heading')) and finite(certificate.get('incline'))
            and endpoints and all(abs(f32(n)-n) <= 1e-6 for n in root)
            and vector_close(root,point(trace.get('position')),1e-3)
            and vector_close(root,point((trace.get('body') or {}).get('object')))
            and vector_close(root,point((trace.get('board') or {}).get('object')))
            and angles_equal(trace.get('body'),native) and angles_equal(trace.get('board'),native)
            and math.hypot(delta[0],delta[2]) <= 32 and abs(delta[1]) <= 32
            and residual <= .120001 and finite(recorded_residual)
            and 0 <= recorded_residual <= .120001 and abs(residual-recorded_residual) <= 1e-5)


def inspect_render_evidence(traces, valid_certificates):
    certificates = {t['frame']:t for t in valid_certificates}
    publications, seen, invalid = {}, set(), []
    binding_samples = [t.get('binding') or {} for t in traces]
    for observed in traces:
        binding = observed.get('binding') or {}
        records = binding.get('lastRenderByPart') or {}
        if not isinstance(records,dict):
            continue
        for role, record in records.items():
            if not isinstance(record,dict) or role not in ('body','board','brace'):
                continue
            frame, publication = record.get('frame'), record.get('publicationId')
            key = (frame,publication,role)
            if key in seen or frame not in certificates:
                continue
            seen.add(key)
            trace = certificates[frame];certificate = trace['certificate']
            root, delta, gfx = point(record.get('physical')), point(record.get('delta')), point(record.get('gfx'))
            certified_root, certified_delta = point(certificate['physical']), point(certificate['certifiedDelta'])
            target = tuple(f32(x+d) for x,d in zip(certified_root,certified_delta))
            residual = truck_residual(gfx,record.get('native'),certificate['visual'])
            names = ('jimmie_original_v1_body_balance042',) if role != 'board' else (
                'jimmie_original_v1_board_balance042','jimmie_stock_v1_board_reverse_balance042')
            valid = (record.get('source') == 'HOOK_ON_OBJECT_RENDER' and record.get('ownerRole') == role
                     and record.get('certificateFrame') == frame and observed.get('frame',-1) >= frame
                     and finite(publication) and publication == int(publication) and publication > 0
                     and vector_close(root,certified_root) and vector_close(delta,certified_delta)
                     and vector_close(gfx,target) and angles_equal(record.get('native'),certificate['native'])
                     and record.get('animationName') in names
                     and record.get('poseFrame') == (trace.get('body') or {}).get('animFrame')
                     and finite(record.get('residual')) and 0 <= record['residual'] <= .120001
                     and abs(record['residual']-certificate['maxTruckResidual']) <= 1e-5
                     and residual <= .121 and binding.get('rendered',0) > 0
                     and binding.get('published',0) >= publication)
            if valid:
                group = publications.setdefault((frame,publication),{})
                group[role] = {'record':record,'independent_native_truck_residual':residual,
                               'observed_at_frame':observed['frame']}
            else:
                invalid.append({'role':role,'frame':frame,'publicationId':publication,
                                'independent_native_truck_residual':residual if math.isfinite(residual) else None})
    paired = []
    for (frame,publication),roles in publications.items():
        if not all(k in roles for k in ('body','board')):
            continue
        body,board = roles['body']['record'],roles['board']['record']
        if (body.get('scene') != board.get('scene') or body.get('sceneKey') != board.get('sceneKey')
                or not vector_close(point(body['delta']),point(board['delta']))):
            continue
        paired.append({'frame':frame,'publicationId':publication,'parts':roles})
    counters = {k:max((b.get(k,0) for b in binding_samples if finite(b.get(k,0))),default=0)
                for k in ('published','rejected','rendered')}
    return {'passed':bool(paired) and not invalid,'paired_publications':len(paired),
            'samples':paired[:12], 'publications':[{'frame':p['frame'],'publicationId':p['publicationId']} for p in paired],
            'invalid_records':invalid[:12],'counters':counters,
            'unmet_reason':None if paired and not invalid else (
                'native-render-record-validation-failed' if invalid else
                'no-native-render-callback-observed' if counters['rendered']==0 else
                'no-matching-body-board-current-certificate-publication'),
            'evidence':'Exact-owner HOOK_ON_OBJECT_RENDER readback, not update-time gfx snapshots',
            'pixel_or_human_visual_acceptance':False}


def inspect_restorations(records, render_evidence):
    publications = {(p['frame'],p['publicationId']) for p in render_evidence['publications']}
    accepted, rejected = {}, []
    for record in records:
        role=record.get('ownerRole');physical=point(record.get('physical'));gfx=point(record.get('gfx'))
        offset=record.get('graphYOffset');frame=record.get('frame');prior=record.get('afterRaisedFrame')
        expected=(physical[0],f32(physical[1]+offset),physical[2]) if physical and finite(offset) else None
        valid=(role in ('body','board') and record.get('source')=='HOOK_ON_OBJECT_RENDER'
               and record.get('postBinding') is True and record.get('currentOwner') is True
               and record.get('sameRenderedObject') is True and finite(frame) and finite(prior) and frame>prior
               and record.get('afterCertificateFrame')==prior
               and (prior,record.get('afterPublicationId')) in publications
               and record.get('motionGrind') is False and record.get('certificatePresent') is False
               and record.get('bindingActive') is False and record.get('crash') is False
               and record.get('externalOwner') is False and vector_close(gfx,expected))
        if valid and role not in accepted:
            accepted[role]=record
        else:
            rejected.append(record)
    return {'passed':set(accepted)=={'body','board'} and not rejected,
            'records':accepted,'rejected_records':rejected,
            'meaning':'Passive post-binding render readback at unshifted physical root plus native graphYOffset'}


def balanced(trace, spec, episode):
    body, board = trace.get('body') or {}, trace.get('board') or {}
    frame = body.get('animFrame')
    return (trace.get('episode') == episode and trace.get('grind') is True
            and trace.get('phase') == 'grind' and trace.get('clip') == 'balance042'
            and trace.get('marioSpeed', 0) >= 8
            and isinstance(frame, (int, float)) and frame == board.get('animFrame')
            and point(body.get('object')) is not None and point(board.get('object')) is not None
            and raised_contact(trace, spec))


def inspect_case(case, spec):
    events, traces, end = case.get('events', []), case.get('traces', []), case.get('end', {})
    episodes = {}
    for event in events:
        episode, kind = event.get('episode'), event.get('kind')
        if kind == 'selected' and (event.get('extra') or {}).get('opportunity') == 'rail':
            episodes[episode] = {'selected': event}
        if episode in episodes:
            episodes[episode].setdefault(kind, event)
    complete, handbacks, partial = [], [], []
    for episode, observed in episodes.items():
        contact = observed.get('rail-contact-observed')
        samples = [t for t in traces if balanced(t, spec, episode)]
        selected, exited, landed = (observed.get(k) for k in ('selected', 'rail-exit', 'landing-observed'))
        full = False
        if contact and exited and landed and raised_contact(contact, spec):
            frames = [e.get('frame', -1) for e in (selected, contact, exited, landed)]
            samples = [t for t in samples if frames[1] <= t.get('frame', -1) <= frames[2]]
            full = (0 <= frames[0] <= frames[1] <= frames[2] < frames[3]
                    and frames[1] <= end.get('routeCutoffFrame', -1) and bool(samples)
                    and (landed.get('extra') or {}).get('opportunity') == 'rail'
                    and landed.get('grounded') is True
                    and not any(k in observed for k in ('cancelled', 'landing-unconfirmed', 'rail-stall-handback')))
            if full:
                complete.append({'episode': episode, 'selected': selected, 'contact': contact,
                                 'exit': exited, 'landing': landed, 'moving_balance_samples': samples})
        refusal = observed.get('cancelled')
        stall = observed.get('rail-stall-handback')
        reason = ((refusal or stall or {}).get('extra') or {}).get('reason')
        safe_reason = reason in ('fresh-clearance-refused', 'exit-changed', 'no-clear-dismount',
                                'raised-presentation-clearance-refused', 'raised-dismount-clearance-refused')
        if safe_reason and contact and raised_contact(contact, spec):
            returned = [t for t in traces if t.get('frame', -1) > (refusal or stall)['frame']
                        and t.get('taskActive') is False and not t.get('grind')
                        and not t.get('crash') and (t.get('position') or {}).get('grounded') is True]
            if returned:
                handbacks.append({'episode': episode, 'reason': reason, 'contact': contact,
                                  'release': refusal or stall, 'observed_grounded_return': returned[0],
                                  'completed_journey': False})
        if not full:
            partial.append({'episode': episode, 'kinds': list(observed),
                            'raised_contact': bool(contact and raised_contact(contact, spec)),
                            'moving_balance_samples': len(samples), 'reason': reason})
    certificate_samples = [t for t in traces if t.get('certificate') is not None]
    valid_certificates = [t for t in certificate_samples if valid_certificate(t,spec)]
    supported_grind_samples = [t for t in traces if t.get('grind') is True and raised_contact(t,spec)]
    certified_journeys = [j for j in complete if any(valid_certificate(t,spec) for t in j['moving_balance_samples'])]
    render_evidence = inspect_render_evidence(traces,valid_certificates)
    completed_render_samples = [sample for sample in render_evidence['publications']
                               if any(j['contact']['frame'] <= sample['frame'] <= j['exit']['frame']
                                      for j in certified_journeys)]
    render_evidence['completed_journey_pair_samples'] = len(completed_render_samples)
    if render_evidence['passed'] and not completed_render_samples:
        render_evidence['passed'] = False
        render_evidence['unmet_reason'] = 'no-render-pair-on-completed-journey'
    restoration_evidence=inspect_restorations(case.get('restorations',[]),render_evidence)
    placement = case.get('placement') or {}
    floors = placement.get('floorSamples') or []
    settled_samples = [t for t in traces if t.get('settling') is True
                       and t.get('frame', -1) > end.get('routeCutoffFrame', -1)]
    last = settled_samples[-15:]
    natural_settle = (len(last) == 15
                     and all(b['frame'] == a['frame']+1 for a, b in zip(last, last[1:]))
                     and all(t.get('taskActive') is False and not t.get('crash')
                             and t.get('marioGrounded') is True and t.get('marioSpeed', math.inf) < 1
                             and (t.get('position') or {}).get('grounded') is True for t in last))
    checks = {
        'validated_initial_floor_route': (case.get('placementCount') == 1 and placement.get('valid') is True
            and placement.get('oneInitialPlacement') is True and placement.get('level') == spec['level']
            and placement.get('area') == spec['area'] and len(floors) >= 10
            and all(f.get('valid') is True and abs(f.get('height', -11000)-spec['floor']) <= 24 for f in floors)),
        'native_movement': (end.get('nativeMovement') is True and end.get('marioDistance', 0) > 500
            and end.get('movingFrames', 0) > 120 and end.get('maxMarioSpeed', 0) > 16
            and end.get('waypointsReached', 0) >= 2),
        'native_map_identity': bool(traces) and all(t.get('level') == spec['level'] and t.get('area') == spec['area'] for t in traces),
        'raised_top_moving_balance_journey': bool(complete),
        'fresh_shifted_envelope_certificates': (bool(valid_certificates)
            and len(valid_certificates) == len(certificate_samples)
            and all(valid_certificate(t,spec) for t in supported_grind_samples)),
        'certified_completed_journey': bool(certified_journeys),
        'natural_grounded_settling': (end.get('settled') is True and end.get('stableGroundTicks', 0) >= 15
            and 15 <= end.get('releasedInputTicks', -1) <= 180 and natural_settle),
    }
    return {'checks': checks, 'journeys': complete, 'safe_live_clearance_handbacks': handbacks,
            'partial_episodes': partial, 'crash_frames': end.get('crashFrames'),
            'certificate_samples': len(certificate_samples), 'valid_certificate_samples': len(valid_certificates),
            'render_hook_evidence': render_evidence, 'restoration_evidence':restoration_evidence,
            'gfx_snapshots_only': True, 'rendered_acceptance': False}


def parse(log):
    cases, policy, completion = {}, None, None
    malformed = []
    for line in log.splitlines():
        if '[raised-rails] ' not in line:
            continue
        payload = line.split('[raised-rails] ', 1)[1]
        try:
            kind, raw = payload.split(' ', 1)
            event = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            malformed.append(payload[:160])
            continue
        if kind == 'policy':
            policy = event
        elif kind == 'COMPLETE':
            completion = event
        elif event.get('case'):
            c = cases.setdefault(event['case'], {'events': [], 'traces': [], 'restorations': [], 'placementCount': 0})
            if kind == 'placement':
                c['placement'] = event;c['placementCount'] += 1
            elif kind == 'event':
                c['events'].append(event)
            elif kind == 'trace':
                c['traces'].append(event)
            elif kind == 'case-end':
                c['end'] = event
            elif kind == 'baseline-restoration':
                c['restorations'].append(event)
    return cases, policy or {}, completion, malformed


def source_checks(inputs, run, harness=HARNESS):
    runtime = ROOT/'mods/jimmie'
    packaged = run/'game/mods/jimmie'
    required = list(RUNTIME)
    # Require any presentation modules actually packaged by the final runtime too.
    required += sorted(n for n in inputs.get('package_files', {})
                       if n.endswith('.lua') and ('presentation' in n or 'render_probe' in n)
                       and n not in required)
    exact = {n: (runtime/n).is_file() and (packaged/n).is_file()
             and inputs.get('package_files', {}).get(n) == sha(runtime/n)
             and (n == 'main.lua' or sha(packaged/n) == sha(runtime/n)) for n in required}
    declared = inputs.get('harnesses') or {}
    harness_exact = len(declared) == 1 and declared.get(str(harness)) == sha(harness)
    main = (runtime/'main.lua').read_text(encoding='utf-8-sig')
    body = harness.read_text(encoding='utf-8-sig').replace('__MAIN_SHA__', sha(runtime/'main.lua')).replace(
        '__CONTROLLER_SHA__', sha(runtime/'original_motion_controller.lua'))
    expected = main+'\n;(function()\n'+body+'\nend)()\n'
    # Runner uses Python text mode, whose newline translation is platform-native.
    expected_bytes = expected.replace('\n', '\r\n').encode() if __import__('os').linesep == '\r\n' else expected.encode()
    assembled_exact = (packaged/'main.lua').read_bytes() == expected_bytes
    outside = re.sub(r'-- BEGIN_INITIAL_PLACEMENT.*?-- END_INITIAL_PLACEMENT', '', body, flags=re.S)
    forbidden = (r'm\.(?:pos|vel)\.[xyz]\s*=', r'PHYS\s*=', r'PHYS\.[a-zA-Z]+\s*=',
                 r'set_mario_action\s*\(', r'obj_set_gfx_pos\s*\(', r'originalOutcomes\s*=',
                 r'math\.random(?:seed)?\s*=', r'\.pendingRail\s*=', r'\.task\s*=')
    source_safe = all(not re.search(pattern, outside) for pattern in forbidden)
    return {
        'exact_runtime_sources': all(exact.values()),
        'exact_declared_harness': harness_exact,
        'exact_assembled_main_no_extra_injection': assembled_exact,
        'no_post_placement_state_forcing': source_safe,
        'exact_runner_source': inputs.get('runner_sha256') == sha(ROOT/'tools/run_jimmie_fork_headless.py'),
        'exact_verifier_input': inputs.get('raised_rails_verifier_sha256') == sha(Path(__file__)),
    }, exact


def verify(run, roomy=False):
    specs=ROOMY_CASES if roomy else CASES
    harness=ROOMY_HARNESS if roomy else HARNESS
    variant='roomy' if roomy else 'strict'
    inputs = json.loads((run/'input.json').read_text())
    native = json.loads((run/'report.json').read_text())
    cases, policy, completion, malformed = parse((run/'stdout.log').read_text(errors='replace'))
    checks = {
        'native_report_passed': native.get('passed') is True,
        'personal_unchanged': native.get('checks', {}).get('personal_unchanged') is True,
        'no_lua_errors': native.get('checks', {}).get('no_lua_errors') is True,
        'native_controller_routes': inputs.get('native_controller_routes') is True,
        'not_seeded_contact': inputs.get('controlled_rail_contact') is False,
        'normal_crash_not_overridden': (inputs.get('forced_outcome_miss_in_terrain') is False
            and inputs.get('forced_outcome_miss_in_rail_physics') is False
            and policy.get('failCount') == 75 and policy.get('failOutOf') == 1000
            and policy.get('normalRandomUnmodified') is True),
        'policy_no_held_state_or_seed': policy.get('heldStates') is False and policy.get('seededRail') is False,
        'bounded_normal_settling': policy.get('routeFrames') == 600 and policy.get('neutralSettleFrames') == 15
            and policy.get('maxSettleFrames') == 180,
        'both_routes_complete': completion is not None and set(cases) == set(specs),
        'explicit_fixture_variant':policy.get('fixtureVariant')==variant,
        'no_malformed_harness_records': not malformed,
        'exact_executed_engine': inputs.get('engine_sha256') == sha(run/'game/sm64coopdx.exe') == native.get('engine_sha256'),
    }
    identities, exact = source_checks(inputs, run, harness);checks.update(identities)
    results = {}
    for name, spec in specs.items():
        results[name] = inspect_case(cases.get(name, {}), spec)
        checks.update({name+'_'+k: v for k, v in results[name]['checks'].items()})
    native_routes_passed = all(checks.values())
    render_checks = {name+'_native_render_hook':results[name]['render_hook_evidence']['passed'] for name in specs}
    render_checks.update({name+'_baseline_restoration':results[name]['restoration_evidence']['passed'] for name in specs})
    checks.update(render_checks)
    return {'passed': all(checks.values()), 'fixture_variant':variant, 'native_routes_passed':native_routes_passed,
            'render_hook_acceptance':all(render_checks.values()), 'checks': checks, 'run': str(run),
            'engine_sha256': inputs.get('engine_sha256'), 'runtime_source_match': exact,
            'runtime_sources': {n: inputs.get('package_files', {}).get(n) for n in exact},
            'harness_sha256': sha(harness), 'verifier_sha256': sha(Path(__file__)),
            'cases': results, 'rendered_acceptance': False, 'limits': LIMITS+' Overall pass additionally requires real body/board render-hook readback on both maps. Even passing hook evidence is not pixel or human visual acceptance.'}


def self_test():
    def fixture():
        rail = {'a': dict(x=-2300, y=603.756, z=-1043.5), 'b': dict(x=-2120, y=603.756, z=-1043.5),
                'shapeSource': 'static-surface-edge', 'visual': {'a': dict(x=-2653,y=614,z=-1043),
                    'b': dict(x=-2039,y=614,z=-1044), 'source': 'verified-static-alpha',
                    'level': 'LEVEL_CASTLE', 'area': 1}}
        def event(kind, frame):
            return {'episode': 1, 'kind': kind, 'frame': frame, 'rail': copy.deepcopy(rail),
                    'position': dict(x=-2250,y=603.756,z=-1043.5), 'extra': {'opportunity':'rail'}, 'grounded':True}
        events = [event(k, f) for k, f in [('selected',1),('rail-contact-observed',2),('rail-exit',5),('landing-observed',9)]]
        trace = event('sample',3);trace.update(grind=True,phase='grind',clip='balance042',marioSpeed=20,
            body={'animFrame':3,'object':dict(x=-2250,y=603.756,z=-1043.5)},
            board={'animFrame':3,'object':dict(x=-2250,y=603.756,z=-1043.5)})
        return {'events':events,'traces':[trace],'end':{'routeCutoffFrame':600}}
    def certificate_fixture():
        trace = fixture()['traces'][0]
        root = tuple(f32(trace['position'][k]) for k in ('x','y','z'))
        visual = {k:copy.deepcopy(trace['rail']['visual'][k]) for k in ('a','b')}
        a,b = point(visual['a']),point(visual['b'])
        line = tuple(y-x for x,y in zip(a,b));length2=sum(n*n for n in line)
        t = sum((x-y)*d for x,y,d in zip(root,a,line))/length2
        center = tuple(x+t*d for x,d in zip(a,line))
        heading = math.atan2(line[0],line[2])
        native = {'yaw':(math.floor(heading*32768/math.pi)-16384)%65536,'pitch':0,'roll':0}
        yaw = math.floor(native['yaw']/16)*2*math.pi/4096
        anchor = (-3.1*math.sin(yaw),3.1,-3.1*math.cos(yaw))
        delta = tuple(c-r-v for c,r,v in zip(center,root,anchor))
        vec = lambda q:dict(zip(('x','y','z'),q))
        certificate = {'physical':vec(root),'certifiedDelta':vec(delta),'visual':visual,'native':native,
                       'heading':heading,'incline':0,'certificateFrame':3,'method':'finite-native-shifted-envelope',
                       'radius':116,'top':360}
        certificate['maxTruckResidual']=truck_residual(tuple(x+d for x,d in zip(root,delta)),native,visual)
        trace.update(certificate=certificate,kind='rail',position=vec(root))
        for role in ('body','board'):
            trace[role].update(native);trace[role]['object']=vec(root)
        records={}
        for role in ('body','board'):
            records[role]={'ownerRole':role,'source':'HOOK_ON_OBJECT_RENDER','frame':3,'certificateFrame':3,
                           'publicationId':1,'scene':1,'sceneKey':'castle','physical':vec(root),
                           'gfx':vec(tuple(f32(x+d) for x,d in zip(root,delta))), 'delta':vec(delta),'native':native,
                           'animationName':'jimmie_original_v1_'+role+'_balance042','poseFrame':3,
                           'residual':certificate['maxTruckResidual']}
        observation={'frame':4,'binding':{'available':True,'published':1,'rendered':2,'lastRenderByPart':records}}
        return trace,observation
    def restoration_fixture():
        records=[{'ownerRole':role,'source':'HOOK_ON_OBJECT_RENDER','postBinding':True,'currentOwner':True,
                  'sameRenderedObject':True,'frame':5,'afterRaisedFrame':3,'afterCertificateFrame':3,
                  'afterPublicationId':1,'physical':dict(x=10,y=20,z=30),'gfx':dict(x=10,y=24,z=30),
                  'graphYOffset':4,'motionGrind':False,'certificatePresent':False,'bindingActive':False,
                  'crash':False,'externalOwner':False} for role in ('body','board')]
        return records,{'publications':[{'frame':3,'publicationId':1}]}
    class VerifyTests(unittest.TestCase):
        def test_real_raised_journey(self):
            self.assertEqual(len(inspect_case(fixture(),CASES['castle_banister'])['journeys']),1)
        def test_low_ledge_cannot_pass(self):
            c=fixture();c['events'][1]['position']['y']=512
            self.assertFalse(inspect_case(c,CASES['castle_banister'])['journeys'])
        def test_visual_mismatch_cannot_pass(self):
            c=fixture();c['events'][1]['rail']['visual']['a']['x']=-818
            self.assertFalse(inspect_case(c,CASES['castle_banister'])['journeys'])
        def test_wrong_episode_cannot_supply_balance(self):
            c=fixture();c['traces'][0]['episode']=2
            self.assertFalse(inspect_case(c,CASES['castle_banister'])['journeys'])
        def test_no_observed_landing_cannot_pass(self):
            c=fixture();c['events'].pop()
            self.assertFalse(inspect_case(c,CASES['castle_banister'])['journeys'])
        def test_header_never_means_rendered(self):
            self.assertIs(inspect_case(fixture(),CASES['castle_banister'])['rendered_acceptance'],False)
        def test_clearance_handback_not_journey(self):
            c=fixture();c['events']=c['events'][:2]
            c['events'].append({'episode':1,'kind':'cancelled','frame':4,'extra':{'reason':'fresh-clearance-refused'}})
            c['traces'].append({'frame':6,'taskActive':False,'position':{'grounded':True}})
            result=inspect_case(c,CASES['castle_banister'])
            self.assertFalse(result['journeys']);self.assertEqual(len(result['safe_live_clearance_handbacks']),1)
        def test_nonfinite_contact_refused(self):
            c=fixture();c['events'][1]['position']['y']=math.nan
            self.assertFalse(inspect_case(c,CASES['castle_banister'])['journeys'])
        def test_fresh_certificate_and_actual_hook_readback(self):
            t,o=certificate_fixture()
            self.assertTrue(valid_certificate(t,CASES['castle_banister']))
            self.assertTrue(inspect_render_evidence([t,o],[t])['passed'])
        def test_final_contact_exit_tick_certificate_allowed(self):
            t,_=certificate_fixture();t['phase']='exit'
            self.assertTrue(valid_certificate(t,CASES['castle_banister']))
        def test_certificate_stale_frame_refused(self):
            t,_=certificate_fixture();t['certificate']['certificateFrame']=2
            self.assertFalse(valid_certificate(t,CASES['castle_banister']))
        def test_certificate_released_grind_refused(self):
            t,_=certificate_fixture();t['grind']=False
            self.assertFalse(valid_certificate(t,CASES['castle_banister']))
        def test_certificate_native_angles_mismatch_refused(self):
            t,_=certificate_fixture();t['body']['yaw']+=64
            self.assertFalse(valid_certificate(t,CASES['castle_banister']))
        def test_update_snapshot_cannot_substitute_for_hook(self):
            t,o=certificate_fixture()
            for r in o['binding']['lastRenderByPart'].values():r['source']='HOOK_UPDATE'
            self.assertFalse(inspect_render_evidence([t,o],[t])['passed'])
        def test_body_only_hook_does_not_pass_pair(self):
            t,o=certificate_fixture();del o['binding']['lastRenderByPart']['board']
            self.assertFalse(inspect_render_evidence([t,o],[t])['passed'])
        def test_mismatched_publications_do_not_pair(self):
            t,o=certificate_fixture();o['binding']['published']=2
            o['binding']['lastRenderByPart']['board']['publicationId']=2
            self.assertFalse(inspect_render_evidence([t,o],[t])['passed'])
        def test_stale_render_certificate_refused(self):
            t,o=certificate_fixture();o['binding']['lastRenderByPart']['board']['certificateFrame']=2
            self.assertFalse(inspect_render_evidence([t,o],[t])['passed'])
        def test_wrong_native_gfx_readback_refused(self):
            t,o=certificate_fixture();o['binding']['lastRenderByPart']['board']['gfx']['y']+=1
            self.assertFalse(inspect_render_evidence([t,o],[t])['passed'])
        def test_dummy_zero_render_counters_explicitly_unmet(self):
            t,_=certificate_fixture();t['binding']={'published':3,'rendered':0}
            result=inspect_render_evidence([t],[t])
            self.assertFalse(result['passed']);self.assertEqual(result['unmet_reason'],'no-native-render-callback-observed')
        def test_roomy_case_keeps_identical_assertion_spec(self):
            self.assertEqual(ROOMY_CASES['castle_banister_roomy'],CASES['castle_banister'])
            self.assertNotIn('castle_banister',ROOMY_CASES)
        def test_baseline_restoration_pair(self):
            records,evidence=restoration_fixture()
            self.assertTrue(inspect_restorations(records,evidence)['passed'])
        def test_restoration_still_shifted_refused(self):
            records,evidence=restoration_fixture();records[1]['gfx']['y']+=3
            self.assertFalse(inspect_restorations(records,evidence)['passed'])
        def test_restoration_other_object_refused(self):
            records,evidence=restoration_fixture();records[1]['sameRenderedObject']=False
            self.assertFalse(inspect_restorations(records,evidence)['passed'])
        def test_restoration_needs_prior_verified_publication(self):
            records,evidence=restoration_fixture();evidence['publications']=[]
            self.assertFalse(inspect_restorations(records,evidence)['passed'])
        def test_restoration_update_snapshot_refused(self):
            records,evidence=restoration_fixture();records[1]['source']='HOOK_UPDATE'
            self.assertFalse(inspect_restorations(records,evidence)['passed'])
        def test_missing_route_fails(self):
            self.assertFalse(any(inspect_case({},CASES['castle_banister'])['checks'].values()))
    return unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(VerifyTests)).wasSuccessful()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run',nargs='?',type=Path);p.add_argument('--self-test',action='store_true');p.add_argument('--roomy',action='store_true',help='Verify the separately labeled roomy Castle fixture with unchanged assertions');a=p.parse_args()
    if a.self_test:
        return 0 if self_test() else 1
    if a.run is None:
        p.error('Supply an existing private run or --self-test')
    run=a.run.resolve()
    if not run.is_relative_to((ROOT/'build/jimmie-runs').resolve()) or not run.is_dir():
        p.error('Run must be an existing directory inside this checkout build/jimmie-runs')
    result=verify(run,roomy=a.roomy)
    (run/'raised-rails-verified.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
