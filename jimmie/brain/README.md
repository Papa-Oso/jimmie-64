# Jimmie's brain

The part of Jimmie 64 that decides whether Jimmie speaks, what the line is for, what the words
are, and gets it to the game in time. It lives in `jimmie-64/brain` and builds its own copy of the
game; it does not change `jimmie-64/main`, the saves, or any earlier build.

## Play it

Double-click **Play Jimmie.cmd**. It starts the brain, then the game, with its own save in
`profile/`. Type `/j16 16` in the game's chat for the 16-star run, `/j16 free` for exploring.

Double-click **Bake New Lines.cmd** (game closed, about an hour) whenever you want him to have
more to say. Each run adds a new batch; nothing already in the pool is repeated.

## How he works

```
game (Lua link) --what happened--> memory --> rules --> director --plan--> game
                                                           ^
                                              the pool: lines written and voiced ahead
```

1. **The game reports what it saw** and who did it: Mario's stars, deaths, falls, hits and swims;
   Jimmie's tricks, bails and the moment he commits to a spot. (`lua/jimmie_brain_link.lua`)
2. **Memory** keeps counts for this visit, streaks, a mood that fades, and what he has audibly said.
   A line counts only when the game confirms it played. A warp wipes what belonged to the room.
3. **Rules** (`jimmie_brain/data/rules.json`) decide when he talks. The most specific matching rule
   wins ("third death in a row here" beats "Mario died"), then rolls its chance. A lost roll is
   silence. Tuning his timing is editing that one file.
4. **The director** works out, after every event, what he would say to each thing that could happen
   next, and hands the game that plan with the sounds already loaded. When the event fires the game
   answers on the same frame with no round trip.
5. **Where the words come from**, in order of how real they are:
   - **Recordings** that ship with the game (`data/bank.json`), including ten original stream cuts.
   - **His everyday reactions** (`data/staples.json`): things he says constantly, word for word,
     counted from the streams ("Oh my god." 421 times, "Fuck." 349, "Holy shit!" 331).
   - **His own sentences** (`data/real_lines.json`): several hundred things he said on stream, word
     for word, picked by hand and filed under the moments and places they fit. These are what make
     him sound like himself; add to this file before asking the model for more.
   - **New lines** written for each situation and each place by the 12B model, shown real lines of
     his making the same move, then checked and edited (`work/pool/lines.jsonl`).
   - **Lore bits** (Carrier, honey oil, greasy old bees, Pink Bitch of Lansing, Peach).
   Everything without a recording is spoken by the voice clone.

6. **What he talks about** (`data/topics.json`). Lines get topics from the words in them. The place
   and what just happened suggest topics, and after he says a line he tends to stay on its topic for
   a while, so chatter follows a thread instead of jumping around.

7. **Talking to him** (`data/chat.json`). Type in the game's chat and he answers out loud about a second
   later, with the words shown in chat too. A greeting, a compliment, a dig, a laugh or a question
   each get one of his real replies to his own stream chat. If the message names one of his bits he
   does the bit, and if it is about something he has a real line on (pizza, his car, being tired),
   he usually says that line. For about 95 things people ask a companion (how old are you, why do
   you skate, where's the star, are you real) there are answers written ahead of time in
   `data/answers.json`: drafted by the model, edited by hand, never stating a fact about the real
   Jimmie. The typed message is matched to the closest question. Nothing is written or voiced
   during play: on this PC a live answer takes 10 to 14 seconds and fills the graphics card, so
   every answer is already in the pool.

### Why lines are made before play

The writer model needs 7.9 GB and the voice 4.6 GB; the card has 12 GB and Windows uses 3. They
cannot run together, and neither can answer inside half a second. So `bake_all.py` runs them in
turn before play, and during play nothing heavy runs at all. `python play.py --live` still runs
the writer and voice during play for experiments.

The bake has four steps (`python -m jimmie_brain.bake write|judge|voice|report`):

- **write**: for every rule, and every place for rules about places, ask for candidates and reject
  any that coach, mention pace or records, use speedrun jargon, swap who did what, invent a count,
  or touch an owner veto.
- **judge**: the model, as an editor, strikes lines that do not fit their moment. Lines lifted whole
  from a stream are dropped. The model ends nearly every line on "son" or "dude"; he does it about
  one time in ten, so the tag is removed from the excess.
- **voice**: the clone records each line, then a speech recogniser that has not seen the script
  listens to it. A take that does not say its words is redone, then dropped.
- **report**: how the written lines compare with speech from streams the writer never saw.

## Keeping up with the stream

`python tools/keep_up.py` (game closed) finds his new streams, transcribes them, picks up to 30 new
sentences of his that stand on their own, adds them to `data/real_lines.json` marked "auto", voices
them and runs the tests. What it added is listed in `docs/KEEPUP_LOG.md`. A scheduled task in the
Claude app runs it on Monday and Thursday at 4:30 am and reads over what was added. `--dry` shows
what it would add without changing anything.

## Checks

```
..\.venv\Scripts\python.exe -B -m unittest discover -s tests     44 tests, including the Lua link
..\.venv\Scripts\python.exe -B -m jimmie_brain scenes            the rule table on 26 matched scenes
..\.venv\Scripts\python.exe -B play.py --smoke 75                boot into the castle grounds, no sound, print what happened
..\.venv\Scripts\python.exe -B play.py --smoke 115 --sound --capture
..\.venv\Scripts\python.exe -B tools\measure_latency.py sessions\<that session>
```

Results so far are in `docs/STATUS.md`, with what was measured and what was not.

## Files

```
Play Jimmie.cmd, Bake New Lines.cmd   the two things to double-click
play.py, bake_all.py                  what they run
jimmie_brain/                         the package (standard library only, apart from the voice)
  data/rules.json   his timing            data/bank.json     recordings and lore bits
  data/staples.json his everyday lines    data/veto.json     owner vetoes
  data/scenes.json  matched test scenes   data/chat.json     how he reads typed chat
  data/answers.json prepared answers to typed questions
  data/topics.json  what lines are about  data/real_lines.json  his own sentences
lua/                                  the game-side link and its install snippet
tools/build_game.py                   makes build/game from the parent build
tools/measure_latency.py              event-to-sound timing from a captured session
tools/speaker_pass.py, train_adapter.py   for the fine-tune experiment (not run)
work/                                 corpus, the pool and its audio (generated, not saved to git)
build/, profile/, sessions/           the game copy, its save, and session logs (generated)
docs/STATUS.md                        where things stand
docs/SPEEDRUN.md                      the 16-star proof: record inputs on the port itself
docs/BUILD_ORDERS.md                  the original step list; kept for history, superseded by STATUS.md
```
