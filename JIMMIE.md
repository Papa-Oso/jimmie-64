# Jimmie 64

A fork of [sm64coopdx](https://github.com/coop-deluxe/sm64coopdx) that adds Jimmie: a
skateboarding companion for Super Mario 64 who talks like a real person. Mario is the player;
Jimmie skates alongside, does 50 named tricks, grinds, manuals and combos, bails, calls his shots,
and answers what you type in chat.

Read [JIMMIE_NOTICE.md](JIMMIE_NOTICE.md) first: this is an unofficial fan project, the character
is a real streamer used with his permission, and his voice in the game is an AI clone.

## Play it (Windows)

You need your own legally obtained **Super Mario 64 (US) ROM**. None is included and none will be.

**The quick way:** download `Jimmie-64-windows.zip` from this repository's Releases page, unzip it,
double-click **Play Jimmie 64**, and drag your `.z64` ROM onto the game window when it asks.

**Or build it yourself:**

1. Build the game the way sm64coopdx is built on Windows (MSYS2 MinGW64; see the port's own
   [README](README.md)), with Jimmie's native parts switched on:

       make -j JIMMIE_NATIVE_HEAD=1 DISCORD_SDK=0 COOPNET=0 UPDATER=0

2. Put Jimmie's extra files beside the built game and check everything is there:

       python jimmie/setup_jimmie.py

3. Start it. This starts Jimmie's brain, then the game:

       python jimmie/brain/play.py

   The first time, the game shows its own screen asking for your ROM. Drag your `.z64` file onto it.

Just play: a clock runs from the moment you pick a file, and goes away by itself if you are
clearly not doing a 16-star run. Type anything in the game's chat to talk to him.

### Nintendo Switch Pro Controller

Hold **ZL** to crouch (N64 Z). Tilt the **right stick** more than halfway up, down, left, or right
to press the corresponding N64 C button. To change one, open **Options → Controls → N64 Binds**,
select its right-stick binding, then tilt the stick or press the button you want to use.
If you have multiple controllers connected, pick the one you're using under **Options → Controls → Gamepad**.

## What is in here

| Folder | What it is |
|---|---|
| everything else | sm64coopdx, with Jimmie's changes to the game program under `src/` (files named `jimmie_*`) |
| `mods/jimmie/` | the Jimmie mod: following, skating, tricks, rails, crashes, the link to his brain, his recorded clips |
| `jimmie/brain/` | what decides when he speaks and what he says, with his lines and the voiced line pool. Start with [its README](jimmie/brain/README.md). |
| `jimmie/movement/` | the code that generates his tricks and motion |
| `jimmie/title/` | his title-screen voice clips |

## What is not in here

- **A ROM or anything taken from one.** You bring your own.
- **The recording used to clone his voice, and the transcripts of his streams.** Never.

## Status

A personal project, played on one machine. Whether the steps above work on a clean computer has
not been proven yet. See [jimmie/brain/docs/STATUS.md](jimmie/brain/docs/STATUS.md) for what has
been measured and what has not.
