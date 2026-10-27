# plus4-canvas HMI project

Our own minimal TJC project for the Plus 4 screen (TJC8048X250_011, 800x480). One blank page `canvas`, no timers, no touch components: Python draws everything (`src/klipmi/canvas/`). Built with the TJC "USART HMI" editor 1.68.2.

- `plus4-canvas.HMI`: editor project (encoding utf-8, orientation 0)
- `plus4-canvas.tft`: compiled firmware (656,888 B: pictures 82,157 B, fonts 76,068 B, no errors or warnings; 28 pictures; sha256 `f3669c15...3f2e`)
- `fonts/*.zi`: generated fonts (editor font tool, anti-aliasing box ticked)
- `assets/svg/`: Material Symbols (Apache-2.0) source icons; `assets/pics/`: PNGs rendered by `tools/hmi_assets.js` (`node tools/hmi_assets.js`, needs Chrome, no packages)
- Inter is SIL OFL: `Inter-4.0.zip` from github.com/rsms/inter/releases (not committed; installed per user, only needed to regenerate the fonts)

## Program.s (runs at power-up)
```
bauds=921600
recmod=0
bkcmd=2
sendxy=1
dim=100
printh 00 00 00 ff ff ff 88 ff ff ff
page canvas
```
The screen therefore boots at 921600 baud (QIDI's firmware boots at 115200).

## Fonts (ids as in the editor's font list)
| id | font | size | characters |
|---|---|---|---|
| 0 | Inter Regular | 16 | ASCII 32-126 |
| 1 | Inter Regular | 20 | ASCII |
| 2 | Inter Regular | 24 | ASCII |
| 3 | Inter Regular | 32 | ASCII |
| 4 | Inter SemiBold | 48 | `0123456789.-:%C /+` |
| 5 | Inter SemiBold | 96 | `0123456789.-:%C /+` |
| 6-9 | Inter Light | 16, 20, 24, 32 | ASCII (default for light text on dark faces) |
| 10-13 | Inter SemiBold | 16, 20, 24, 32 | ASCII (dark ink on bright faces; `gfx.text()` swaps Light for SemiBold when the ink is darker than its background) |

Ids 0-3 (Inter Regular) are unused: on the glass Regular looked heavy and ragged on dark faces, Light is clean there, and only SemiBold stays readable as dark ink on the cyan accent.

## Pictures (ids)
Pictures have no alpha, so every icon strip and corner sheet is baked against one background colour from `Theme` (`src/klipmi/canvas/gfx.py`). Pick the id that matches the surface you draw on.

Icon strips (white icons, one cell per icon, cell width = height = size; `xpic x,y,size,size,k*size,0,id`):
cell order `nozzle bed chamber fan light spool home control files box gear play pause stop up down left right check warning`

| ids 0-5 (24 px) | ids 6-11 (32 px) | background |
|---|---|---|
| 0 | 6 | BG |
| 1 | 7 | SURFACE |
| 2 | 8 | SURFACE2 |
| 3 | 9 | RAISED |
| 4 | 10 | ACCENT |
| 5 | 11 | ACCENT_DIM |

Corner sheets, 96x100 px (fill colour over backdrop colour). Radii 4, 6, 8, 10, 12, 16, 20, 24 are stacked top to bottom (y offsets 0, 4, 10, 18, 28, 40, 56, 76); in a radius row the four r x r corners sit side by side at x = k*r, k = 0 top-left, 1 top-right, 2 bottom-left, 3 bottom-right. The corner outside the shape shows the backdrop colour.

| id | fill | backdrop |
|---|---|---|
| 12 | SURFACE | BG |
| 13 | SURFACE2 | SURFACE |
| 14 | RAISED | SURFACE |
| 15 | SURFACE2 | BG |
| 16 | RAISED | BG |
| 17 | ACCENT | BG |
| 18 | ACCENT | SURFACE |
| 19 | ACCENT_DIM | SURFACE |
| 20 | ERR_DIM | SURFACE |
| 21 | BG | SURFACE |

Second icon strip set (appended later, pictures 22-27; `ICON2_*` in `gfx.py`), cell order `mmu wifi info refresh lock`, drawn in three backdrops only:

| ids 22-24 (24 px) | ids 25-27 (32 px) | background |
|---|---|---|
| 22 | 25 | SURFACE |
| 23 | 26 | SURFACE2 |
| 24 | 27 | ACCENT |

Adding or reordering pictures renumbers the ids: keep this table, `assets/pics/pics.json` and the canvas code in step.

## Rebuild
1. `node tools/hmi_assets.js` (only if icons or palette changed), delete the pictures in the editor's picture list, re-add them one at a time in the id order above.
2. Compile (toolbar), File > "output production file" with the folder set to this directory.
3. Flash: `~/klipmi/venv/bin/python ~/klipmi/flash_tft.py --baud 921600 plus4-canvas.tft` on the printer (this firmware boots at 921600; a screen still on QIDI firmware that was not driven by klipmi answers at 115200, so use `--baud 115200 --upload-baud 921600`).

## Measured on the real screen (2026-10-27, 921600 baud, `tools/bench.py`, 60 commands per test, ms per command incl. flow control)
| command | window 256 B | window 900 B (what the writer uses) |
|---|---|---|
| `xstr` Inter16 400x30 / Inter20 / Inter24 / Inter32 | 6.8 / 9.8 / 10.2 / 11.2 | 4.9 / 6.6 / 7.2 / 9.2 |
| `xstr` Digit48 300x60 / Digit96 400x110 | 6.2 / 12.2 | 5.1 / 8.8 |
| `xstr` Inter16 80x24 ("215 C") | 4.1 | 2.1 |
| `pic` icon strip 480x24 / 640x32 / corner sheet 96x100 | 1.4 / 1.7 / 2.1 | 0.8 / 1.1 / 1.8 |
| `xpic` icon 24x24 / 32x32, corner 12x12 / 24x24 | 2.7 | 0.9 |
| `picq` 24x24 | 2.1 | 0.9 |

Earlier QIDI-firmware figures: fill ~0.9 ms, `cirs` r10 3 ms / r30 11 ms, `xstr` 5-7 ms. So an `xpic` corner costs a third of a disc, and Inter text costs about the same as the old fonts. No `pic`/`xpic`/`xstr` id error came back, so all 6 fonts and 22 pictures resolve. Upload: 525,816 B in 9 s at 921600.

A full page (about 200 commands) is on the glass in 130-410 ms (`preview.py --device`): home 326, control 357, files 139, box 413, system 322, printing 129.

Anti-aliasing: the font tool's "anti-aliasing" box changes the generated file by only 68 B (Microsoft Sans Serif 16, ASCII: 2518 B on, 2450 B off), so the stored glyphs look the same either way; look at the glass to judge whether text is smoothed. Rounded corners and icons are anti-aliased regardless (they are pictures).
