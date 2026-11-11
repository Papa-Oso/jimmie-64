# The 16-star proof

## Where it stands

Route awareness works on fixtures: 16 stars, both keys and the final Grand Star are detected,
with warps and placed collectibles doing the travelling. What is missing is one continuous,
input-driven run through final Bowser. The attempt so far replays a public N64 input movie on the
PC port. It diverges at the first movement inside the castle: the original holds the fixed camera
at yaw 29169 while the port pans to 7635, and stick direction depends on camera yaw.

## Stop syncing the N64 movie

That movie is a tool-assisted run: frame-exact inputs tuned to one emulator's timing. The port
differs in intro length (four samples already had to be skipped), in this camera transition, and
it will differ again at every load and cutscene. Each fix buys the distance to the next
divergence, and a camera patch made only to keep a foreign movie in sync is not a fix to the
game. A stair BLJ leaves no slack for any of it. This path proves nothing about Jimmie even when
it works.

## Record on the port instead

The engine already has what is needed: `jimmie_route_pad.c` feeds controller values through a
pipe each poll and reports Mario's state back. Three small additions:

1. **Recorder.** With an environment switch set, append each poll's four controller bytes to a
   file, plus the state snapshot every 30 polls. Normal controller in, file out.
2. **Determinism check.** Record 60 seconds of ordinary play from a fresh file. Replay it three
   times through the existing pipe tool. Pass: the state snapshots are identical at every poll.
   If they are not, find the source first (candidates: anything in the companion that reads the
   wall clock or an unseeded random number and can touch Mario; Jimmie's speech timing must never
   affect Mario's physics).
3. **Replay-then-play.** Feed a recorded prefix at full speed, then hand over to the live
   controller and keep recording. With determinism this is a save state built from inputs: a hard
   section can be retried from just before it without replaying the run by hand. Add a test-only
   slow-motion factor on the same switch.

With those, a non-runner can assemble the run segment by segment, at reduced speed, including the
MIPS clip and the stair BLJs, and the result is one input file that replays start to finish on
the release build. That file is the proof, and afterwards a permanent regression test for every
route trigger and every line Jimmie says along the way. Label it honestly: assembled with
slow-motion and retries on the port, not a real-time human run.

A real runner playing the private build once with the recorder on gives the same artifact faster,
and is the only thing that answers "does he feel right to a runner". The two are not substitutes.

## What the run mode should feel like

Per the owner: no pace, splits or PB talk in his mouth, no coaching, no technique names. The rule
table encodes that as sparseness, not as a different character: stars get a reaction a quarter of
the time, idling gets none, arrivals get none except the castle greeting and the final Bowser
stage, a hard jump occasionally gets Carrier at the worst moment, and the sixteenth star, the
keys and the Grand Star always land. The writer rejects any line that mentions time, records or
technique, whatever the model produces.
