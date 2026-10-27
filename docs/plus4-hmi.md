# Plus 4 stock HMI notes

Derived from `xindi_800_480.HMI` v1.7.1 with Nextion2Text (needs a patched copy: unknown model ID `0x7527dcfa`, component type 70, UTF-8 text). Button meanings are inferred from layout and the Bunny-Box shims; confirm on the printer.

## Stock Box pages (already in the HMI)
`zero_box_page` (text "BOX not connected", exit/guide/load/unload for the external spool), `one_box_page` (1 box, about 107 components), `multi_box_page` (several boxes), `box_setting` (detect on insert / on boot / auto refill), `box_drying`, `dry*` (prepare/select/tips/warn/finish), `slot_params` (vendor/filament/colour per slot), `tool_select` (includes "BOX drying"), `box_error_pop`, `box_link_pop`, `box_unlink_pop`, `box_update_pop`.

### one_box_page component map (host fills these; page ids 0x65 events listed per button)
| Component | Role |
|---|---|
| `t0` | label "spool holder" (external spool, column 0) |
| `t19..t22` | slot labels 1A..4A |
| `t1, t5, t6, t13, t14` | per-column state text ("?" = unknown) for holder, 1A..4A |
| `p0..p4` | spool icon per column, `p5..p9` selected-frame pictures per column |
| `b9..b13` (ids 44-48) | whole-column touch areas, send 10..14; `b4..b8` send 5..9; `b14..b17` (slot settings) send 71..74 |
| `b1` / `b2` / `b3` | buttons "unload", "load", "retract" send 2 / 3 / 4; `b0` exit sends 1 |
| `t17` / `t18` / `t26` | box temperature current / target, humidity |
| `t16` | heating state icon |
| `t64, t65, t66` | material, "max temp", value (e.g. PLA, 20 C) |
| `t51 / t63` | slot or RFID tag text (e.g. `QDE_004_016 1A`) |
| `t52..t62` | error texts: load failed, unload failed, extruder sync failed, RFID read failed, tangle/clog, box self-check failed, filament used up, auto refill failed |
| `t50` | retry |
| `t38` | temperature keypad range label `[0, 65] C`, keys `b39..b50` |
| `t24, t25, t30, gm0` | popups and loading animation |
| `b33..b37` | bottom nav (home / control / files / tools / settings), send 33..37 |
Visibility and text come from the host (`vis`, `tN.txt=`); the page init code only hides everything and sets language strings from the global `lang`.

## Mapping implemented so far (`klipmi/features/mmu.py`)
| Touch id | Stock button | G-code |
|---|---|---|
| 10..14 | column areas (holder, 1A..4A) | select only (frame `p5..p9`) |
| 3 | load | `MMU_CHANGE_TOOL GATE=n STANDALONE=1` |
| 4 | retract | `MMU_UNLOAD` (`MMU_SELECT GATE=n` first if n is not the current gate) |
| 2 | uninstall | `MMU_EJECT GATE=n` |
| 1 | exit | back to `main` |

Not mapped yet: ids 5..9 and 71..74 (slot parameter / refresh buttons), `slot_params`, `box_setting`, drying pages, error texts `t52..t62`.
