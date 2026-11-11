# Where Jimmie's brain stands

2026-11-09, 23:30. Everything here was run on this PC from `jimmie-64\brain`.

## What you can do now

Double-click `Play Jimmie.cmd`. He reacts to his own tricks and bails, Mario's stars, deaths,
falls, hits and swims, arriving somewhere, and standing around. He has 968 written lines, 147 of
his everyday reactions and the shipped recordings to draw on.

## The first play test (22:41, 2.6 minutes, the owner playing)

Two complaints, both confirmed in the log and both acted on:

- **"He hardly talked."** 4 lines in 2.6 minutes. The odds were too low (arriving 45%, a death 40%,
  filling silence 8% every two seconds after 45 quiet seconds) and three chosen lines never played,
  reason unrecorded. Now: arriving 90%, deaths and stars 85%, silence is filled after about 12
  seconds, he may speak from further away, a pending line waits 7 seconds instead of 4, and every
  line that fails to come out is logged with its reason. Automated check afterwards: 10 lines in
  70 seconds, none missed. Not yet replayed by a person.
- **"It kept freezing."** The voicing job had the graphics card at 93-99% during that session, which
  averaged 36 ms a frame against a normal 33 with one stretch at half speed. With voicing finished,
  a 74-second run held 33.3 ms a frame with no frame over 120 ms, with the brain and without it.
  The link also now loads at most two sounds per quarter second and logs any long frame. Do not
  run `Bake New Lines.cmd` while playing.

## The second play test (2026-11-10, 1.5 minutes, the owner playing through the FJ64 shortcut)

"Seemed like fresh lines, though a little sparse on creativity. Maybe more chatter, longer lines."
The log agreed: 9 lines, among them "Oh my god, okay.", "Holy shit, okay." and two about "that
mountain". A third of the written place lines open "I mean", "Holy shit" or "God damn", 83% are six
words or fewer, and the lore bits only fired when Mario stood still. Changes:

- **120 things he really said on stream, word for word**, picked by hand for the moment they fit
  (`jimmie_brain/data/real_lines.json`), many of them full sentences. The clone speaks them. They
  come up about 2.5 times as often as a written line. Picked by his speech habits; the speaker
  check has still not been run, so one could be a guest's.
- Written place lines with the overused openers stay in the pool but come up far less.
- He fills a quiet stretch after about 7 seconds (was 12) and stands-around chatter starts after 6.
- Lore bits can come up while exploring (`wander_bit`), not only when Mario is idle.
- Automated check: 14 lines in 120 seconds, 8 of them his real ones, one lore bit, none missed,
  one frame over 120 ms. Not yet replayed by a person.
- Voicing long lines four at a time ran out of graphics memory; use `bake_all.py --voice-only --batch 1`.

The owner played that version and said "its incredible", then asked for more. A second round added
211 real lines the same way: 331 in the file, 330 voiced ("Dude, there is just no way." never
passed the listening check). Automated check after it: 11 lines in 120 seconds, 9 of them real,
none missed, no frame over 120 ms. About 4,000 filtered stream lines are still unread in
`work/real_candidates2.json` (made by `work/more_candidates.py`).

Third play test (2.8 minutes, 13 lines, 10 real, one long frame): "pretty good... some things
were a little out of place, like why did he say that?" The out-of-place ones were tangents that
point at something unseen ("I've been avoiding it all fucking day."). 41 such lines were taken out
of general chatter (12 removed entirely, the rest kept only for the moments they fit; 319 lines
remain), and chatter now picks a line about the current place 55% of the time, a tangent 30%.
Also seen: a 48-second silence while Jimmie was far from Mario. The brain chose lines but the game
only speaks them when he is near; not changed.

After that test the owner asked for him to be "wrangled in a bit, like he knows what he's said
before... feels more aware", without stifling him. Two changes, neither replayed by a person:

- **A sense of topic** (`jimmie_brain/data/topics.json`). Lines get topics from the words in them
  (130 of the 319 real lines have one). The place and what just happened suggest topics, and after
  he says a line he stays on its topic for 45 seconds, 60% of the time. Automated run: "Did you
  have any fucked up dreams or no?" was later followed by "Shit, I need some sort of caffeine." and
  "We kind of had a late start to the day, but we got a nice good fucking sleep in."
- **He speaks when far away.** The voice then comes from a point 1,800 units from Mario in his
  direction (`lua/install_brain.lua`). Patched into `build/game` in place, not by a rebuild, so the
  movement session's ollie files were left alone. Not tested far away: the automated run has Mario
  standing still.

Not built: him referring back to an earlier line in words (a callback).

A third round added 47 real lines for the thin moments (stars, keys, the ending, the 16-star run,
Mario leaving mid-trick): 366 in the file, 364 voiced. Two tests were added (39 pass). No game run
was made after this round because another session had the game open; the pool loads offline.

The FJ64 desktop shortcut now opens `Play Jimmie.cmd`; the old build is "FJ64 (old build)".

## The fourth play test (2026-11-10, 5.3 minutes, the owner playing)

"Honestly it's all incredible. Love the lines." The log: 40 lines, 30 of them his real ones, none
missed, no long frames, 22 of the 40 on a topic. This was the first play with topic threading,
far-away talk, the third batch of lines and the movement session's animation changes.

He then asked for Jimmie to answer the game's text chat. Built the same day, not yet tried by a person:

- **The game reports what the player types** (`lua/jimmie_brain_link.lua`, `self.chat`), commands
  left out. Patched into `build/game` in place; `tools/build_game.py` was not rebuilt.
- **The brain reads the message** (`jimmie_brain/data/chat.json`): a greeting, goodbye, compliment,
  dig, laugh, question or plain statement, plus any of his bits it names and what it is about.
- **He answers with something he really said to his own chat**: 145 replies added to
  `real_lines.json` under seven `chat_` rules, every one checked word for word against the
  transcripts and voiced (511 real lines in the file). A question or statement that shares a word
  or topic with one of his other real lines gets that line about 85% of the time ("do you like
  pizza?" gets "Dude, I haven't had a pizza in so long.").
- He answers even if he has only just spoken, the reply waits for him to finish a sentence, and the
  words also appear in the chat box.
- Checked by: two new tests (41 pass), sample messages against the real pool offline, and a
  60-second boot of the build with no Lua errors. **Nobody has typed to him in the game yet**, so
  the hook firing on a real chat message is unproven.
- Known weak spot: a question he has no line about gets a generic "I don't know, man." or yes/no.

**Answers written during play were measured and rejected** (`work/live_trial.py`, game closed):

| Setup | Write | Voice one line | Card memory, no game |
|---|---|---|---|
| Writer wholly on the card, no voice | 0.8-1.1 s | - | 11.5 of 12.2 GB |
| 20 of the writer's layers on the card, voice loaded | 3.0-5.3 s | 6.0-8.1 s | 11.4-11.6 GB |
| 12 layers on the card, voice loaded | 4.0-5.8 s | 5.8-7.4 s | 10.2-10.6 GB |
| Writer off the card, voice loaded | 5.0-8.6 s | 5.8-7.2 s | 7.8-8.0 GB |

An answer would arrive 10 to 14 seconds after the message with the card nearly full before the game
takes its share. The voice alone is 6 to 8 seconds, so a smaller writer would not fix it. Not tried
with the game running.

**Instead: answers prepared ahead** (`jimmie_brain/data/answers.json`). 94 kinds of question in 350
phrasings, 263 answers (260 voiced; the two "I'm Jimmie" answers and one other never passed the listening check). The 12B model drafted about ten per question (`work/answers_write.py`,
1,060 candidates); they were cut by hand to the ones that answer the question in his rhythm. Left
out: anything stating a fact about the real Jimmie (his age, home, work, family, phone number,
birthday, politics, bands) - those questions get a dodge - invented anecdotes, and a flat claim to
be human when asked if he is an AI. A typed message is matched to the closest phrasing by its
telling words (stdlib only, `Director._answer_for`); "match" in the file sets how close. A dig or a
compliment keeps its own real reply unless the message is almost exactly a prepared question.
Checked by a new test (42 pass) and sample messages. These are written lines in the clone's voice,
not his words. Not yet tried by a person.

## Measured

| What | Result | How |
|---|---|---|
| Event to first audible sample, reactions | 40 lines: median 92 ms, 95th percentile 95 ms, slowest 96 ms. Target was 500 ms. | Seven two-minute sessions with the game's own audio output recorded; each line's waveform located in the recording. `work/latency.txt` |
| Same, including idle lines | 53 of 54 lines located: median 92 ms, slowest 98 ms | Same sessions |
| Called shot, then a bail, then the payoff | Seen twice: "So easy." then "Fuck me."; "Okay, here we go." then "Oh, shit." Payoff on the same frame as the bail. | Sessions `20261109-220629` and `20261109-221028` |
| Called shot, then a landing | Seen in every session, for example "Let's do it." then "Easy shit." | Same |
| Lua errors | None in nine sessions | `stdout.log` of each |
| Tests | 42 pass, including the game-side link under a mocked engine | `python -m unittest discover -s tests` |
| Rule table | 26 of 26 matched scenes choose the intended rule or silence | `python -m jimmie_brain scenes` |
| Lines written | 1,366 in 7.5 minutes; 971 kept after editing (161 struck as not fitting, 35 lifted whole from a stream, 199 duplicates once the name tag was removed) | `work/pool/lines.jsonl`, `lines-all.jsonl` |
| Voice takes that say their words | 994 voiced, 97% on the first try; 3 never passed and are left out | `work/pool/voice.json`, `voice-dropped.json` |

All sessions were automated: the game booted into the castle grounds with Mario standing still.
Nobody played. Stars, deaths, falls, water and the 16-star mode were not exercised in a live run;
their code paths are covered only by the tests.

## Not good enough yet

- **Written lines are easy to tell from his real speech.** A simple classifier separates them from
  lines in streams the writer never saw 96% of the time; two sets of his real lines score 61%. Part
  of that is topic (he talks to chat about everything; these are all game reactions), but two
  causes are real: the written lines swear about twice as often as he does (10.6% of words against
  5.1%) and end on "son/dude/buddy" in 24% of lines against his 10%. His word-for-word everyday
  reactions cover about half of quick reactions, which hides some of this in play.
- **8% of written lines of four words or more also appear in a training stream.** These are short
  common phrases; longer lifts were removed.
- **Only ten lines are his real voice.** The rest is the clone. "Watch this shit." and "Fuck." are
  the clone too; the original cuts are not wired in.
- **Nobody who knows him has listened.** The speech recogniser confirms the words, not that it
  sounds like him.

## Not done

- A person playing: stars, deaths, water, the castle, and `/j16 16` through final Bowser.
- The listening test with people who know his streams (`python -m jimmie_brain packet`).
- The fine-tune experiment (a model trained on his speech against the stock one, transcript search off).
- Recording a runner's inputs on the port itself (`docs/SPEEDRUN.md`).
- Speaker check of the transcripts: donation text-to-speech and guests are still mixed into the
  lines the writer learns from.

## Next steps, most valuable first

1. Play for ten minutes and list the lines you hated. Wordings go in `data/veto.json`; timing
   complaints are edits to `data/rules.json`.
2. Cut his real "Fuck.", "Holy shit!", "Oh my god.", "Come on." and "Watch this shit." out of the
   streams and name them in `data/bank.json`. Each real cut replaces a cloned one from then on.
3. Trim the pool toward his real swearing rate, the same way the name tags were trimmed, and re-score.
4. Run the speaker pass, then the fine-tune comparison.
