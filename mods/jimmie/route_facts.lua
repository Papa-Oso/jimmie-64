-- Source-linked facts only. No navigation, save writes, or player control.
-- Course numbers are canonical 1-based; star_id is mission number, never selected act.
local F = {
    ["schema"] = 1,
    ["verified_on"] = "2026-11-05",
    ["profile"] = "documented beginner 16-star reference, adaptable to observed detours",
    ["sources"] = {
        ["uk16"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/16_Star",
            ["summary"] = "Standard no-LBLJ route and beginner Dorrie-for-Dark-World-reds branch",
            ["verified_on"] = "2026-11-05"
        },
        ["rta16beginner"] = {
            ["url"] = "https://www.sm64rta.info/star-beginner/16star-guide/",
            ["summary"] = "Independent community beginner route; stage order may differ",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_chain"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Behind_Chain_Chomp%27s_Gate",
            ["summary"] = "Mission6; beginner post route and optional bomb clip",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_wall"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Blast_Away_the_Wall",
            ["summary"] = "Mission6; cannonless setups and Wild Blue backup",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_blue"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Shoot_into_the_Wild_Blue",
            ["summary"] = "Mission3; beginner tree and sideflip approach",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_king"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Chip_off_Whomp%27s_Block",
            ["summary"] = "Mission1; selecting star1 respawns the king on collected saves",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_tower"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/To_the_Top_of_the_Fortress",
            ["summary"] = "Mission2; choose star2 for tower and no owl",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_cage"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Fall_onto_the_Caged_Island",
            ["summary"] = "Mission5; owl spawn requires selecting3-6 after stars1+2",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_ccm"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Cool,_Cool_Mountain",
            ["summary"] = "Three-star castle door; no-LBLJ route uses Wall Kicks and Penguin",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_wallkicks"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Wall_Kicks_Will_Work",
            ["summary"] = "Mission6; beginner lower route vs backflip wallkick",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_penguin"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Li%27l_Penguin_Lost",
            ["summary"] = "Mission2; slope movement and version-dependent star spawn",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_ssl"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Shifting_Sand_Land",
            ["summary"] = "Hidden wall entrance and mission-dependent Klepto/tornado state",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_bird"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/In_the_Talons_of_the_Big_Bird",
            ["summary"] = "Mission1 must be selected for Klepto's star",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_pyramid"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Shining_Atop_the_Pyramid",
            ["summary"] = "Mission2, outside pyramid top",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_lll"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Lethal_Lava_Land",
            ["summary"] = "Basement fireball painting and optional log-star route",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_puzzle"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/8-Coin_Puzzle_with_15_Pieces",
            ["summary"] = "Mission3; beginner/intermediate options",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_hmc"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Hazy_Maze_Cave",
            ["summary"] = "Black-pool entrance; Toad12; collect Toad before15 or reload basement",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_exit"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/A-Maze-ing_Emergency_Exit",
            ["summary"] = "Mission5; camera matters; Rolling Rocks backup",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_rocks"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Watch_for_Rolling_Rocks",
            ["summary"] = "Mission6; boulder RNG requires reaction",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_dorrie"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Swimming_Beast_in_the_Cavern",
            ["summary"] = "Mission1; beginner alternative; expert strat version-dependent",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_toad"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/HMC_Toad",
            ["summary"] = "Toad near HMC entrance appears at12 stars",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_ddd"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Dire,_Dire_Docks",
            ["summary"] = "Sub completion moves painting; second Bowser completion removes sub",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_sub"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/Board_Bowser%27s_Sub",
            ["summary"] = "Mission1; standard back-sub approach",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_mips"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/MIPS_Clip",
            ["summary"] = "Door clip technique reference",
            ["verified_on"] = "2026-11-05"
        },
        ["uk_blj"] = {
            ["url"] = "https://ukikipedia.net/wiki/RTA_Guide/50_Star_Door_and_Endless_Staircase_BLJs",
            ["summary"] = "Both final upstairs skips; input tutorial intentionally not copied",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_courses"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/levels/course_defines.h",
            ["summary"] = "Course numbers; save index is one less",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_levels"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/levels/level_defines.h",
            ["summary"] = "Level number enumeration; do not confuse level and course ids",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_save"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/save_file.c#L625-L701",
            ["summary"] = "Star bitmask reading and secret-star mapping",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_flags"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/save_file.h#L85-L113",
            ["summary"] = "Exact key/door/Toad/MIPS flags",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_keys"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/mario_actions_cutscene.c#L1000-L1006",
            ["summary"] = "Unlocking consumes key bit and sets unlocked-door bit",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_keyaward"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/save_file.c#L569-L584",
            ["summary"] = "Boss1/2 key grant checks owned OR door already unlocked",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_hardcoded"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/hardcoded.c#L55-L77",
            ["summary"] = "CoopDX default pause-exit-anywhere TRUE; acts enabled; infinite stairs70",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_thresholds"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/hardcoded.c#L150-L158",
            ["summary"] = "Default Toad12/25/35; MIPS15/50",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_lua_fields"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/autogen/lua_definitions/structs.lua#L169-L185",
            ["summary"] = "Exact Lua-exposed uppercase ToadStar1Requirement/MipsStar1Requirement",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_lua_example"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/mods/star-road/hardcoded.lua#L54-L72",
            ["summary"] = "Bundled mod demonstrates actual field access and altered requirements",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_mips"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/behaviors/mips.inc.c#L34-L55",
            ["summary"] = "First rabbit requires threshold and first MIPS secret star uncollected; evaluated at object initialization",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_blj"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/mario.c#L1024-L1033",
            ["summary"] = "Negative long-jump velocity remains uncapped",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_blj_sh"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/mario_actions_moving.c#L2062-L2069",
            ["summary"] = "Backward-speed landing fix exists only under VERSION_SH",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_sub"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/behaviors/ddd_sub.inc.c#L1-L5",
            ["summary"] = "Sub removed if key2 owned OR upstairs door unlocked",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_ddd_gate"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/paintings.c#L1650-L1674",
            ["summary"] = "DDD bit0 and moved-back flag control painting",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_star_exit"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/interaction.c#L930-L945",
            ["summary"] = "Actual stay-in-level setting changes collection/exit behavior",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_star_modes"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/pc/network/network.h#L76-L87",
            ["summary"] = "0=leave,1=stay,2=nonstop",
            ["verified_on"] = "2026-11-05"
        },
        ["engine_pause"] = {
            ["url"] = "https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/game/ingame_menu.c#L2979-L3009",
            ["summary"] = "Pause exit checks level setting and Lua hook approval",
            ["verified_on"] = "2026-11-05"
        }
    },
    ["courses"] = {
        [1] = {
            ["name"] = "Bob-omb Battlefield",
            ["level"] = 9,
            ["entry"] = "Use Bob-omb Battlefield's painting in the castle's first-floor room.",
            ["source_id"] = "uk16"
        },
        [2] = {
            ["name"] = "Whomp's Fortress",
            ["level"] = 24,
            ["entry"] = "Use Whomp's Fortress's one-star door in the lower castle lobby.",
            ["source_id"] = "uk16"
        },
        [4] = {
            ["name"] = "Cool, Cool Mountain",
            ["level"] = 5,
            ["entry"] = "Use Cool, Cool Mountain's three-star castle door and painting.",
            ["source_id"] = "uk_ccm"
        },
        [6] = {
            ["name"] = "Hazy Maze Cave",
            ["level"] = 7,
            ["entry"] = "Go to the basement's unnumbered door and enter the black pool for Hazy Maze Cave.",
            ["source_id"] = "uk_hmc"
        },
        [7] = {
            ["name"] = "Lethal Lava Land",
            ["level"] = 22,
            ["entry"] = "Use the red fireball painting in the basement for Lethal Lava Land.",
            ["source_id"] = "uk_lll"
        },
        [8] = {
            ["name"] = "Shifting Sand Land",
            ["level"] = 8,
            ["entry"] = "Use the hidden wall at the basement hall's end near Lethal Lava Land's painting.",
            ["source_id"] = "uk_ssl"
        },
        [9] = {
            ["name"] = "Dire, Dire Docks",
            ["level"] = 23,
            ["entry"] = "Reach the water painting behind the basement's thirty-star door for Dire, Dire Docks.",
            ["source_id"] = "uk_ddd"
        },
        [16] = {
            ["name"] = "Bowser in the Dark World",
            ["level"] = 17,
            ["entry"] = "Use the eight-star door for Bowser in the Dark World.",
            ["source_id"] = "uk16"
        },
        [17] = {
            ["name"] = "Bowser in the Fire Sea",
            ["level"] = 19,
            ["entry"] = "Use the opening exposed after the Dire, Dire Docks painting retreats.",
            ["source_id"] = "uk_ddd"
        },
        [18] = {
            ["name"] = "Bowser in the Sky",
            ["level"] = 21,
            ["entry"] = "Reach the final upstairs staircase and Bowser in the Sky.",
            ["source_id"] = "uk16"
        }
    },
    ["objectives"] = {
        ["bob_chain"] = {
            ["objective_id"] = "bob_chain",
            ["kind"] = "star",
            ["course"] = 1,
            ["level"] = 9,
            ["star_id"] = 6,
            ["label"] = "Behind Chain Chomp's Gate",
            ["direction_text"] = "Head to Chain Chomp's wooden post; use the post-ground-pound route to open the gate.",
            ["source_id"] = "uk_chain",
            ["source_ids"] = {"uk_chain"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 1,
                ["star_id"] = 6
            },
            ["caution"] = "post route preferred to unverified bomb-clip setup"
        },
        ["wf_wall"] = {
            ["objective_id"] = "wf_wall",
            ["kind"] = "star",
            ["course"] = 2,
            ["level"] = 24,
            ["star_id"] = 6,
            ["label"] = "Blast Away the Wall",
            ["direction_text"] = "Head to the plank beside the wall star; use a learned cannonless setup. Wild Blue is the documented missed-attempt backup.",
            ["source_id"] = "uk_wall",
            ["source_ids"] = {"uk_wall"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 2,
                ["star_id"] = 6
            },
            ["caution"] = "precise setup requires practice/video and compatible collision behavior"
        },
        ["wf_blue"] = {
            ["objective_id"] = "wf_blue",
            ["kind"] = "star",
            ["course"] = 2,
            ["level"] = 24,
            ["star_id"] = 3,
            ["label"] = "Shoot into the Wild Blue",
            ["direction_text"] = "Use the tree to reach Wild Blue's star platform; the sideflip approach is recommended for beginners.",
            ["source_id"] = "uk_blue",
            ["source_ids"] = {"uk_blue"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 2,
                ["star_id"] = 3
            }
        },
        ["wf_king"] = {
            ["objective_id"] = "wf_king",
            ["kind"] = "star",
            ["course"] = 2,
            ["level"] = 24,
            ["star_id"] = 1,
            ["label"] = "Chip Off Whomp's Block",
            ["direction_text"] = "Climb to King Whomp at the summit; finish the boss objective and collect his star.",
            ["source_id"] = "uk_king",
            ["source_ids"] = {"uk_king"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 2,
                ["star_id"] = 1
            },
            ["caution"] = "On a collected save, select star1 to spawn the king.",
            ["required_act"] = 1
        },
        ["wf_tower"] = {
            ["objective_id"] = "wf_tower",
            ["kind"] = "star",
            ["course"] = 2,
            ["level"] = 24,
            ["star_id"] = 2,
            ["label"] = "To the Top of the Fortress",
            ["direction_text"] = "After King Whomp, select star2 and climb the new tower to its top star.",
            ["source_id"] = "uk_tower",
            ["source_ids"] = {"uk_tower"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 2,
                ["star_id"] = 2
            },
            ["caution"] = "requires the tower act; do not assume same geometry in act1",
            ["prerequisites"] = {"wf_king"},
            ["required_act"] = 2
        },
        ["wf_cage"] = {
            ["objective_id"] = "wf_cage",
            ["kind"] = "star",
            ["course"] = 2,
            ["level"] = 24,
            ["star_id"] = 5,
            ["label"] = "Fall onto the Caged Island",
            ["direction_text"] = "After stars1 and2, select a later act to spawn the owl; ride it to the caged island.",
            ["source_id"] = "uk_cage",
            ["source_ids"] = {"uk_cage"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 2,
                ["star_id"] = 5
            },
            ["caution"] = "Owl requires stars1+2 completed and selecting3-6; owlless is an optional learned alternative.",
            ["prerequisites"] = {"wf_king", "wf_tower"},
            ["act_range"] = {3, 6}
        },
        ["ccm_wall"] = {
            ["objective_id"] = "ccm_wall",
            ["kind"] = "star",
            ["course"] = 4,
            ["level"] = 5,
            ["star_id"] = 6,
            ["label"] = "Wall Kicks Will Work",
            ["direction_text"] = "Head down to the lower wall-kick route; use the beginner descent instead of the harder backflip setup.",
            ["source_id"] = "uk_wallkicks",
            ["source_ids"] = {"uk_wallkicks"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 4,
                ["star_id"] = 6
            }
        },
        ["ccm_penguin"] = {
            ["objective_id"] = "ccm_penguin",
            ["kind"] = "star",
            ["course"] = 4,
            ["level"] = 5,
            ["star_id"] = 2,
            ["label"] = "Li'l Penguin Lost",
            ["direction_text"] = "Carry the small penguin down to its mother; preserve control across the snowy slopes.",
            ["source_id"] = "uk_penguin",
            ["source_ids"] = {"uk_penguin"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 4,
                ["star_id"] = 2
            },
            ["caution"] = "Mission2/index1; star spawn varies between JP and US."
        },
        ["bitdw_reds"] = {
            ["objective_id"] = "bitdw_reds",
            ["kind"] = "star",
            ["course"] = 16,
            ["level"] = 17,
            ["star_id"] = 1,
            ["label"] = "Bowser in the Dark World Red Coins",
            ["direction_text"] = "Follow the red-coin route through Dark World before entering Bowser's arena.",
            ["source_id"] = "uk16",
            ["source_ids"] = {"uk16"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 16,
                ["star_id"] = 1
            },
            ["caution"] = "Standard intermediate branch only; beginner branch uses Dorrie instead."
        },
        ["ssl_bird"] = {
            ["objective_id"] = "ssl_bird",
            ["kind"] = "star",
            ["course"] = 8,
            ["level"] = 8,
            ["star_id"] = 1,
            ["label"] = "In the Talons of the Big Bird",
            ["direction_text"] = "Select star1 so Klepto has the star; approach the front pillar and recover the bird's star.",
            ["source_id"] = "uk_bird",
            ["source_ids"] = {"uk_bird"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 8,
                ["star_id"] = 1
            },
            ["caution"] = "Mission act must expose Klepto's star.",
            ["required_act"] = 1
        },
        ["ssl_pyramid"] = {
            ["objective_id"] = "ssl_pyramid",
            ["kind"] = "star",
            ["course"] = 8,
            ["level"] = 8,
            ["star_id"] = 2,
            ["label"] = "Shining Atop the Pyramid",
            ["direction_text"] = "Go to the star on top of the pyramid; this is the outside objective, not Inside the Ancient Pyramid.",
            ["source_id"] = "uk_pyramid",
            ["source_ids"] = {"uk_pyramid"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 8,
                ["star_id"] = 2
            }
        },
        ["lll_puzzle"] = {
            ["objective_id"] = "lll_puzzle",
            ["kind"] = "star",
            ["course"] = 7,
            ["level"] = 22,
            ["star_id"] = 3,
            ["label"] = "8-Coin Puzzle with 15 Pieces",
            ["direction_text"] = "Head to the moving puzzle platform; collect its eight red coins for the puzzle star.",
            ["source_id"] = "uk_puzzle",
            ["source_ids"] = {"uk_puzzle"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 7,
                ["star_id"] = 3
            }
        },
        ["hmc_exit"] = {
            ["objective_id"] = "hmc_exit",
            ["kind"] = "star",
            ["course"] = 6,
            ["level"] = 7,
            ["star_id"] = 5,
            ["label"] = "A-Maze-ing Emergency Exit",
            ["direction_text"] = "Head for the emergency-exit ledge; a missed wall-kick attempt can back up to Rolling Rocks.",
            ["source_id"] = "uk_exit",
            ["source_ids"] = {"uk_exit"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 6,
                ["star_id"] = 5
            },
            ["caution"] = "Camera-sensitive route; no precise inputs asserted here."
        },
        ["hmc_rocks"] = {
            ["objective_id"] = "hmc_rocks",
            ["kind"] = "star",
            ["course"] = 6,
            ["level"] = 7,
            ["star_id"] = 6,
            ["label"] = "Watch for Rolling Rocks",
            ["direction_text"] = "Take the boulder route toward its upper star; react to rolling rocks rather than assuming a clear path.",
            ["source_id"] = "uk_rocks",
            ["source_ids"] = {"uk_rocks"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 6,
                ["star_id"] = 6
            }
        },
        ["hmc_dorrie"] = {
            ["objective_id"] = "hmc_dorrie",
            ["kind"] = "star",
            ["course"] = 6,
            ["level"] = 7,
            ["star_id"] = 1,
            ["label"] = "Swimming Beast in the Cavern",
            ["direction_text"] = "Head down to the underground lake for Swimming Beast; this extra star replaces Dark World reds in the beginner route.",
            ["source_id"] = "uk_dorrie",
            ["source_ids"] = {"uk_dorrie", "uk16"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 6,
                ["star_id"] = 1
            },
            ["caution"] = "Do not copy the JP-only expert strategy into US CoopDX."
        },
        ["ddd_sub"] = {
            ["objective_id"] = "ddd_sub",
            ["kind"] = "star",
            ["course"] = 9,
            ["level"] = 23,
            ["star_id"] = 1,
            ["label"] = "Board Bowser's Sub",
            ["direction_text"] = "Swim to the submarine chamber and board Bowser's sub for its top star.",
            ["source_id"] = "uk_sub",
            ["source_ids"] = {"uk_sub", "uk_ddd"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary tutorial and exact engine mission/bit identity",
            ["completion"] = {
                ["kind"] = "star",
                ["course"] = 9,
                ["star_id"] = 1
            },
            ["caution"] = "Unavailable after second key/upstairs-unlocked state removes the submarine; cannot restore by selecting act1."
        },
        ["first_key"] = {
            ["objective_id"] = "first_key",
            ["kind"] = "key",
            ["label"] = "First Bowser key",
            ["direction_text"] = "At eight stars, enter Dark World through the eight-star door, finish the stage, defeat first Bowser and collect his key.",
            ["source_id"] = "engine_keyaward",
            ["source_ids"] = {"engine_keyaward", "engine_keys", "uk16"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary route and engine progress rules",
            ["course"] = 16,
            ["level"] = 17,
            ["arena_level"] = 30,
            ["completion"] = {
                ["kind"] = "flag",
                ["any"] = {"key1", "basementUnlocked"}
            }
        },
        ["toad1"] = {
            ["objective_id"] = "toad1",
            ["kind"] = "star",
            ["label"] = "HMC basement Toad star",
            ["direction_text"] = "Talk to Toad beside HMC's black-pool entrance once twelve stars are available; collect this before the fifteenth star.",
            ["source_id"] = "uk_toad",
            ["source_ids"] = {"uk_toad", "uk_hmc", "engine_thresholds", "engine_flags"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary route and engine progress rules",
            ["course"] = 0,
            ["level"] = 6,
            ["area"] = 3,
            ["completion"] = {
                ["kind"] = "flag",
                ["any"] = {"toad1Collected"}
            }
        },
        ["mips_clip"] = {
            ["objective_id"] = "mips_clip",
            ["kind"] = "gate",
            ["label"] = "MIPS door access",
            ["direction_text"] = "At fifteen stars, use the available yellow rabbit for the thirty-star-door clip; do not collect his star as an extra route star.",
            ["source_id"] = "uk16",
            ["source_ids"] = {"uk16", "uk_mips", "engine_mips", "engine_flags"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary route and engine progress rules",
            ["course"] = 0,
            ["level"] = 6,
            ["area"] = 3,
            ["completion"] = {
                ["kind"] = "access",
                ["course"] = 9,
                ["any"] = {"bitfsDoorUnlocked", "dddMovedBack"}
            }
        },
        ["second_key"] = {
            ["objective_id"] = "second_key",
            ["kind"] = "key",
            ["label"] = "Second Bowser key",
            ["direction_text"] = "After the submarine star opens the way, enter Fire Sea, finish the stage and collect second Bowser's key.",
            ["source_id"] = "uk_ddd",
            ["source_ids"] = {"uk_ddd", "engine_keyaward", "engine_keys", "engine_sub"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary route and engine progress rules",
            ["course"] = 17,
            ["level"] = 19,
            ["arena_level"] = 33,
            ["completion"] = {
                ["kind"] = "flag",
                ["any"] = {"key2", "upstairsUnlocked"}
            }
        },
        ["upstairs_skips"] = {
            ["objective_id"] = "upstairs_skips",
            ["kind"] = "gate",
            ["label"] = "Upstairs door and staircase skips",
            ["direction_text"] = "After the second key, the sixteen-star route requires the fifty-star-door and endless-staircase skips; offer precise coaching only with compatible capability verified.",
            ["source_id"] = "uk_blj",
            ["source_ids"] = {"uk_blj", "engine_blj", "engine_blj_sh", "engine_hardcoded"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary route and engine progress rules",
            ["course"] = 0,
            ["level"] = 6,
            ["completion"] = {
                ["kind"] = "access",
                ["course"] = 18
            }
        },
        ["final_stage"] = {
            ["objective_id"] = "final_stage",
            ["kind"] = "gate",
            ["label"] = "Traverse Bowser in the Sky",
            ["direction_text"] = "Traverse Bowser in the Sky and enter the final boss pipe; red coins are not required for the sixteen-star finish.",
            ["source_id"] = "uk16",
            ["source_ids"] = {"uk16", "engine_levels"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary route and engine progress rules",
            ["course"] = 18,
            ["level"] = 21,
            ["completion"] = {
                ["kind"] = "level",
                ["level"] = 34
            }
        },
        ["final_bowser"] = {
            ["objective_id"] = "final_bowser",
            ["kind"] = "finish",
            ["label"] = "Final Bowser and the grand star",
            ["direction_text"] = "Defeat final Bowser and take the grand star.",
            ["source_id"] = "uk16",
            ["source_ids"] = {"uk16", "engine_levels", "engine_keyaward"},
            ["confidence"] = 0.95,
            ["source_confidence"] = "primary route and engine progress rules",
            ["course"] = 18,
            ["level"] = 34,
            ["completion"] = {
                ["kind"] = "finish"
            }
        }
    },
    ["early"] = {"bob_chain", "wf_wall", "wf_blue", "wf_king", "wf_tower", "wf_cage", "ccm_wall", "ccm_penguin"},
    ["basement"] = {"ssl_bird", "ssl_pyramid", "lll_puzzle", "hmc_exit", "hmc_dorrie", "hmc_rocks"}
}

F.basementStandard = {"ssl_bird","ssl_pyramid","lll_puzzle","hmc_exit","hmc_rocks"}
F.objectives.toad1.completion.secret_mask = 1
F.objectives.wf_wall.alternate = {objective_id="wf_blue",label="Wild Blue backup",
    direction_text="Use the beginner tree approach to Wild Blue if the wall-star attempt is missed.",source_id="uk_wall"}
F.objectives.hmc_exit.alternate = {objective_id="hmc_rocks",label="Rolling Rocks backup",
    direction_text="Rolling Rocks is the documented backup for a missed emergency-exit attempt.",source_id="uk_exit"}
F.objectives.bitdw_reds.alternate = {objective_id="hmc_dorrie",label="Beginner Dorrie branch",
    direction_text="The beginner branch skips Dark World reds and later takes Swimming Beast in Hazy Maze Cave.",source_id="uk16"}
F.sources.uk_bob = {url="https://ukikipedia.net/wiki/RTA_Guide/Bob-omb_Battlefield",
    summary="Bob-omb Battlefield castle entrance",verified_on="2026-11-05"}
F.sources.uk_wf = {url="https://ukikipedia.net/wiki/RTA_Guide/Whomp%27s_Fortress",
    summary="Whomp's Fortress one-star castle door",verified_on="2026-11-05"}
F.courses[1].source_id = "uk_bob"
F.courses[2].source_id = "uk_wf"
return F
