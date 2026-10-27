# Own UI for the Plus 4 screen (design)

## Decision (2026-10-27): draw the UI from the host
The editor route below needs the Windows-only TJC editor for every change, and nothing else can write `.HMI`/`.tft`. A prototype (`tools/canvas_proto.py`) showed that the stock HMI can be used as a blank canvas instead:

- Page `logo` has no components except a timer; `tm0.en=0` stops its 100 s restart.
- `sendxy=1` makes the display report any touch as `0x67 <x:2> <y:2> <press|release> ff ff ff`.
- `fill`, `xstr` (text with solid background, so no clear-then-draw flicker) and `pic` draw everything. Fonts available to the host: ids 0 (largest), 1, 2 only (3+ answer "bad font"). Pictures: whatever the HMI contains.
- `baud=921600` (temporary, back to 115200 on restart) makes it responsive; use `bkcmd=2` and fire-and-forget writes, since the `nextion` library waits for an answer per command (about 100 ms each).
- Redraw only what changed: draw text over its own background, cache what each slot shows.

Result on the real screen: live temperatures and a touch-driven nav bar, no visible flicker, responsive at 921600 baud. Consequences: all pages are Python (buttons are rectangles plus hit tests), English strings live in code, and the HMI is only a resource container (fonts, pictures). Still to do: icons (picture ids), page framework (widgets, hit testing, diffed drawing), port of the Box page. The editor route stays as an option for artwork.

Everything below is the earlier editor-based design; the principles (host owns the text, optional hardware stays optional, small command volume) still hold.

Goal: an English-first UI that is ours end to end, built on QIDI's AGPL-3.0 Plus 4 HMI (`xindi_800_480.HMI`, TJC8048X250_011C, 800x480) and driven by klipmi. Contributors can add other QIDI printers later by adding `ui/<printer>/` and an HMI.

## Principles
1. **The HMI is dumb.** It draws components and reports touches. All text, numbers, colours and visibility come from klipmi over serial. No logic beyond what makes a press feel instant (pressed colour, keypad entry).
2. **No text in the HMI.** Every label is set by the host from one strings table (`klipmi/ui/plus4/strings.py`, English first), so another language is a table, not a new `.tft`. Icons stay as pictures.
3. **Stable names.** Pages and components keep their names across editor saves; code addresses them by name (`page box`, `t_slot1.txt`), never by index.
4. **One touch contract.** Every page has "Send Component ID" on, so any touch arrives as `0x65 <page id> <component id>` (the format the `nextion` TJC protocol already parses). Component ids are fixed per page and listed in the table below.
5. **Optional hardware stays optional.** Pages for chamber, box, drying exist, but klipmi only links to them if Klipper reports the objects.
6. **Small command volume.** The display handles about 10 commands a second. Pages should be laid out so one status update needs few changes.

## Global
- `Program.s`: `bauds=921600`, `recmod=0`, `dim=100`, then `page boot`. Keep the stock `sleep`/`dim` handling.
- Global ints: `lang` (unused for now, kept for strings later), `sel` (selected slot, host-owned).
- Colours: reuse the stock palette (dark grey cards, `38066` blue highlight on the nav bar).
- Nav bar (all main pages): Home, Control, Files, Tools, Settings. Touch ids 33-37 as in the stock UI, so the existing handling carries over.

## Pages (v1)
| Page | Purpose | Notes |
|---|---|---|
| `boot` | splash until Klipper is ready | no touch, host moves on |
| `home` | temperatures, light, e-stop, current job card | from stock `main` |
| `control` | move/home, temperatures, fans, extrude | new, uses stock icons |
| `files` | file list, start print | host pushes rows; 6 rows per page |
| `printing` | progress, layer, time, pause/resume/cancel | thumbnail via `cp0`-style picture |
| `box` | MMU: four slots, selected slot, load/unload/eject, climate | from stock `one_box_page`; slot count fixed at four for v1 |
| `box_slot` | edit one slot: material, colour, spool | from stock `slot_params` |
| `box_dry` | drying: temperature, time, start/stop | from stock `box_drying` |
| `popup` | message and confirm (OK / Cancel) | one page reused for all dialogs, text from host |
| `error` | Klipper shutdown / disconnected, restart buttons | |

Not in v1: Wi-Fi setup, first-run wizard, calibration wizards, account pages (stay in Mainsail).

## Per-page contract (template)
Each page gets a table in `docs/pages/<page>.md`: component name, type, id, set by (host/HMI), source field, touch ids sent. `box` is first, from `hmi-text/one_box_page` of the stock project:
- columns: `t_hold`, `t_s1..t_s4` (solid colour blocks, `bco` = filament colour, `vis` = present), selection frames `p_sel0..p_sel4`
- buttons: `b_exit`, `b_unload`, `b_load`, `b_eject`, column touch areas `b_col0..b_col4`
- climate: `t_temp`, `t_target`, `t_humid`, `p_heat`
- hint/error line `t_hint`, popup `t_popup`

## Editor workflow (manual part)
1. Install the TJC USART HMI editor (Windows) and open `xindi_800_480.HMI` (copy it into `hmi/plus4/`, not committed).
2. Rename pages and components as in the tables; remove pages and code we replace.
3. Delete all text content and event code that sets text; keep images and fonts. Turn on "Send Component ID" per page.
4. Compile, copy the `.tft` out, flash with `tools/flash_tft.py` (about 6 minutes at 921600 baud), run klipmi.
5. Commit the HMI as a release asset (it is 36 MB) and the page tables.

## Host side
- `strings.py`: `STR = {"home.temp_nozzle": "Nozzle", ...}`, one lookup, English only at first.
- Per page: a class that writes its labels once in `init()` and then only values on status updates (using the command diff in `Plus4Page.send`).
- Tests: command lists per page rendered from recorded status samples, as `tests/test_mmu.py` does for the box.

## Open points
- Which stock pages to keep as they are (graphics) versus redraw.
- Fonts: only the stock fonts are available in the project; check English glyph coverage and sizes before laying out text.
- Whether to ship `.tft` per release or only the `.HMI`.
