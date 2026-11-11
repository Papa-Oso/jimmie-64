# Jimmie 64

![The Jimmie 64 start screen](jimmie/readme/start-screen.png)

A skateboarding companion for Super Mario 64 who talks like a real person.

You play Mario. Jimmie skates alongside: he does 50 named tricks, grinds, manuals and combos, bails,
calls his shots, and has something to say about all of it. Type in the game's chat and he answers
out loud.

> **Read first:** [JIMMIE_NOTICE.md](JIMMIE_NOTICE.md). This is an unofficial fan project, not
> affiliated with Nintendo. Jimmie is the streamer floppyjimmie, used with his permission, and his
> voice in the game is an AI clone. Strong language throughout.

## Play it

You need your own **Super Mario 64 (US) ROM** (a `.z64` file). None is included and none will be.

1. Download `Jimmie-64-windows.zip` from [Releases](https://github.com/Papa-Oso/jimmie-64/releases/latest) and unzip it anywhere.
2. Open the `Jimmie 64` folder. Optionally double-click **Add desktop shortcut**.
3. Double-click **Play Jimmie 64**.
4. The first time, the game asks for your ROM. Drag your `.z64` file onto the game window. You only do this once.

Windows 10 or 11, 64-bit. Nothing else needs installing.

## In the game

- Just play. A clock runs from the moment you pick a file. If you are clearly not doing a 16-star
  run it goes away by itself and Jimmie settles into exploring with you. At each star it shows
  how far ahead or behind you are.
- Type anything else in chat to talk to Jimmie: say hello, ask him something, give him a hard time.
- When a newer Jimmie 64 is out, the start screen says UPDATE READY; `Update Jimmie 64.cmd` opens the
  download page. Nothing installs by itself. The check downloads one small public file from this
  repository at start-up and sends nothing about you; with no internet it is skipped.

## Controls

- **Z** is the left trigger (ZL / LT). **R** is the right bumper or right trigger. **L** is the left bumper.
- The **right stick** is the four C buttons. To change one, open **Options → Controls → N64 Binds**,
  select its slot, then tilt the stick or press the button you want.
- On a Nintendo controller, A and B sit in swapped positions compared with an Xbox pad. Rebind them
  in the same menu if jump feels like it is on the wrong button.
- With several controllers connected, pick yours under **Options → Controls → Gamepad**.
- To reset every control, close the game and delete `brain\profile\save\sm64config.txt`.

## What he does

![Jimmie skating beside Mario](jimmie/readme/in-game.png)

- **Skates:** 50 named tricks (flips, shuvits, grabs, spins, grinds and slides, manuals, nollie and
  fakie versions, a few old-school ones), linked into combos, with falls that have a cause.
- **Talks:** several hundred things he really said on stream, picked for the moments they fit, plus
  lines written in his style. He stays on a subject for a while instead of jumping around.
- **Answers:** greetings, digs, questions and anything about his own bits, in the game's chat.
- **Runs:** in the 16-star mode he follows the route with you.

## Build it yourself

This repository is a fork of [sm64coopdx](https://github.com/coop-deluxe/sm64coopdx) and builds the
same way (MSYS2 MinGW64 on Windows), with Jimmie's parts switched on:

    make -j JIMMIE_NATIVE_HEAD=1 DISCORD_SDK=0 COOPNET=0 UPDATER=0
    python jimmie/setup_jimmie.py
    python jimmie/brain/play.py

More in [JIMMIE.md](JIMMIE.md). How his speech works is in [jimmie/brain/README.md](jimmie/brain/README.md).

| Folder | What it is |
|---|---|
| `mods/jimmie/` | the Jimmie mod: following, skating, tricks, rails, crashes, his recorded clips |
| `jimmie/brain/` | what decides when he speaks and what he says, with his lines and voiced line pool |
| `jimmie/movement/` | the code that generates his tricks and motion |
| `src/` | sm64coopdx, with Jimmie's changes to the game program in files named `jimmie_*` |

## What is not here

- A ROM, or anything taken from one.
- The recording used to clone his voice, and the transcripts of his streams.

## Credits

Built on [sm64coopdx](https://github.com/coop-deluxe/sm64coopdx) by the Coop Deluxe team, which
continues sm64ex-coop and rests on the Super Mario 64 decompilation. Everything that makes the port
work is theirs; see their repository for its own documentation and contributors.

Jimmie is floppyjimmie. Go watch him: <https://www.twitch.tv/floppyjimmie>
