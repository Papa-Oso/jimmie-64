# Raised rail presentation helper (offline prototype)

> Later integration note: the prototype and runtime helper now both use canonical LF, SHA256 `764cdfc2335dc0b6db7ffd6ee6a09f65e66d18f91a825de51e8078a71c86b953`. Only the final CRLF changed. Older prototype hashes below identify the preserved raw checkpoint; current native evidence is in docs/jimmie/raised-rails/.

Only new files in this folder are owned by this prototype. No runtime module,
main binding, collision, installed build, Git index or game/UI has been changed.
This adds presentation support for verified handrail/fence tops; it neither
replaces stair/ledge opportunities nor proves a new collision surface exists.

## Handoff API

Load `presentation_anchor.lua` as a returned module. Call `compute` with:

- `root={x,y,z}`: immutable physical root for this frame, never prior gfx output.
- `rail={a={x,y,z},b={x,y,z},verified=true}`: finite verified visual top segment.
  The integrator can adapt `rail.visual.a/b` to this shape. `verified=true` is a
  caller assertion, not an independent geometry, current-scene or collision proof.
- `heading`, `incline`: actual travel heading/incline in radians. Heading must be
  in [-2pi,2pi], incline within +/-pi/3. Either segment direction is accepted.
- `native={yaw,pitch,roll}`: actual emitted integer object angles, signed s16 or
  unsigned u16 spelling. Pitch must be zero. The helper does not recalculate
  emitted angles from ideal visual geometry.
- `clip`: exactly `jimmie_original_v1_board_balance042` or
  `jimmie_stock_v1_board_reverse_balance042`.
- `blend`: [0,1]. `blend(entryProgress,exitRemaining)` supplies a pure min-of-two
  smoothstep envelope; caller owns time, identity, phase and continuity.
- Optional `safetyMargin` [0,32], default 2. Both ends require at least 35.34 plus
  this margin of 3D segment distance. Margin 6.66 gives an inset of 42.

Success returns `ok=true`, `delta`, `fullDelta`, absolute presentation `root`,
`truckCenter`, `truckA/B`, `contactCenter`, `axis`, `inset`, `along`, `length`,
`centerContact`, `exactTruckContact`, `maxTruckResidual`,
`fullBlendTruckResidual` and `contactTolerance`. Failure returns `ok=false` and
an explicit `reason`, with no reusable prior delta. `paired(result)` returns
fresh equal `body/board/brace` delta values, without aliases to each other.

All coordinates must be finite and within +/-32768. Full correction, even when
blend is zero, is rejected above horizontal magnitude 32 or absolute Y 32.
There is no clipping of an excessive correction and no endpoint clamping.
Both actual travel-to-line and emitted board-axis-to-line differences are
bounded by 0.12 units at each 35.34-unit half-span. The emitted board axis must
also face actual travel within 0.0034 radians. Wrong clips, bank, stale emitted
pose, vertical/too-steep or short/degenerate lines and out-of-interior roots fail.

At blend 1 the mean truck anchor is algebraically centered on the visual line.
`centerContact` is false throughout partial entry/exit. `exactTruckContact`
requires blend 1 and mathematical orientation residual below 1e-8; most diagonal
lines do NOT meet this. `fullBlendTruckResidual` reports the quantized orientation
residual used for the <=0.12 admission test. `maxTruckResidual` reports actual
current presented truck distance to the FINITE segment, including partial blend
error. A zero orientation error must not be read as current contact at blend 0.
Native float/table/fixed-matrix rendering precision is not exact-contact proof.

## Source-derived anchor evidence

The two contacts are underside EDGE MIDPOINTS, not literal packed mesh vertices.
Arrays `jimmie_orig_board_board_shade_vtx_007` and `_015` contain vertices 2 and 5
at (+/-57,-17,+17) and (+/-57,-17,-17). They share the edge in triangles (4,5,2)
and (5,0,2), establishing interpolated centerline anchors (+/-57,-17,0).

The raw balance042 board bank has constant translation [0,22,-5] and rotation
[0,0,0]; reverse has the same translation and [32768,0,32768], equivalent to Y180.
The reverse exchanges longitudinal truck endpoints but does not flip root-local
translation. With runtime scale .62, both poses have anchor mean (0,3.10,-3.10)
and half-span 35.34. These are TRUCK contacts, not deck-underside contacts.
Current `jimmie_init` sets scale .62 and graphYOffset=0. Integrator MUST reject
changed scale/graphYOffset, unsupported animation interpolation, or a different
pose rather than silently applying these anchors.

Hashes independently checked by the source tests:

- Board model: `9e104ed61001620ebaa6701f5e120b5f0a4e41034061928d77f13d9bc7f914a6`
- `original_clip_bank.lua`: `168bca45f901d539b99e44cfb105cd600b4644966e635438c7784a007727a684`
- `src/engine/math_util.c`: `674634d8ac43fd7bdf2f5332c919aa16b43df7c7fc1d1a6d10787fd4d387df86`
- `include/trig_tables.inc.c`: `e1e73e0df08c58796d1decb040850b9f5c9997fe78e4f2976a43ace07d51db3b`

The native `sins/coss` index drops the low four s16 bits. The helper models that
quantization, then uses Lua math.sin/cos. Tests compare all 5120 overlapping
native sine/cosine entries; maximum f32 table difference is 2.979808289e-8.
This bounds table approximation, not a complete renderer or collision error.

Fixture expectations independently exercised:

- Castle visible (-818,614,-429) to (-622,614,-429), PHYS (-720,603.756,-429):
  dx=0, dy=7.144, dz=3.10; presentation rootY=610.9.
- BoB visible (-1521,891,2034) to (1288,891,3820), midpoint PHYS Y901:
  dy=-13.1, presentation rootY=887.9. Tests use the actual differing collision
  crest direction (2812,0,1789), not an artificially exact visible-line heading,
  and test both travel directions including reverse clip.

## Required integration gates (not implemented here)

The integrator owns current rail/scene/actor identity, lifecycle, pose selection,
fresh real collision checks and fresh clearance for the SHIFTED WHOLE MODEL,
including swept entry/exit displacement. The existing physical corridor does
NOT prove shifted body/board/brace clearance. Apply no presentation offset when
these checks fail. Never modify PHYS, collision, locomotion root or global actors.

Source-order review by the coordinating engineer found that ordinary
HOOK_UPDATE occurs after render_game and before the next behavior update resets
gfx position. Therefore merely calling obj_set_gfx_pos there is insufficient.
The source-derived integration plan is:

1. Publish one immutable snapshot in update after pose selection, binding the
   current trio, scene, clip, expected physical positions/angles/scale, phase,
   ownership and frame timer to the fresh checked offset.
2. Enable hookRender only for owned body/board/brace. In an owner-filtered
   HOOK_ON_OBJECT_RENDER callback, revalidate snapshot identity, scene, pose,
   frame and absence of crash/rejoin/external ownership before applying each
   object's absolute physical root plus the SAME delta. Never gfx plus delta.
3. Source ordering increments gGlobalTimer after render but before HOOK_UPDATE:
   a snapshot stamped F in update is consumed by next render at the SAME F,
   not F+1. The callback follows uninitialized-gfx reset and precedes matrix
   construction. Integrator must verify this in its actual binding tests.
4. Any invalid lifecycle, identity, ownership, scale, graphYOffset or pose falls
   back to ordinary baseline gfx, clears stale presentation state and retains
   existing stair/ledge behavior. Bind brace separately; a prior update-time
   copy of body gfx does not survive its next behavior reset.

This is a source-derived plan, not a tested hook, native build, rendered,
controller or visual-acceptance result. No game was launched. No runtime module
was copied or profile/allowlist changed. Distribution/rights constraints remain.

## Reproduce offline checks

From this checkout, use an existing Python with lupa's Lua 5.3 module (matching
`lib/lua/include/lua.h`), for example:

    C:/Github/Repositories/jimmie-64/.venv/Scripts/python.exe tools/raised_rails/test_presentation_anchor.py

The test runner writes only stdout and fails closed if pinned evidence changes.
It verifies 10 focused Lua groups: Castle, actual-heading BoB in both directions,
uphill/downhill with reverse clip, finite endpoint insets, strict correction
bounds, blend semantics, native angle quantization, incompatible pose rejection,
nonfinite geometry rejection, and 100-frame immutable/no-accumulation paired
output. Mesh topology, raw bank, scale and trig evidence are checked separately.

## Independent review

The coordinating engineer independently reran the focused suite and rebuilt six
truck endpoint fixtures using actual float32 native sine-table values, the full
C matrix formula and packed-space reverse clip rotation/translation. Castle,
BoB and sloped lines in both directions differed from this helper by at most
1.3371e-6 world units. Helper source hash was stable before/after that read-only
check (`5770648af4c1834291ac45cf0f1ecb19ba92b0ae066a25578bdbd13585c6e1a7`).
This is independent source/math evidence only, not engine rendering acceptance
or shifted-pair collision clearance.
