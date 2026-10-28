# plus4-canvas HMI project

Our own minimal TJC project for the Plus 4 screen (TJC8048X250_011, 800x480). One blank page `canvas`, no timers, no touch components: Python draws everything (`src/klipmi/canvas/`). Built with the TJC "USART HMI" editor 1.68.2.

- `plus4-canvas.HMI`: editor project (encoding utf-8, orientation 0)
- `plus4-canvas.tft`: compiled firmware (919,156 B: pictures 341,209 B, fonts 75,068 B, no errors or warnings; 21 pictures; sha256 `19127271...5b10`)
- `fonts/*.zi`: generated fonts (editor font tool, anti-aliasing box ticked)
- `assets/pics/`: PNGs rendered by `tools/hmi_assets.js` (`node tools/hmi_assets.js`, needs Node and Chrome, no packages). The icons are original 24-unit stroke drawings, kept as SVG paths in that script
- Fonts are generated from Inter (SIL OFL 1.1, licence in `fonts/OFL.txt`): `Inter-4.0.zip` from github.com/rsms/inter/releases, installed in Windows; only needed to regenerate the fonts

## Program.s (runs at power-up)
```
bauds=921600
recmod=0
bkcmd=2
sendxy=1
dim=100
printh 00 00 00 ff ff ff 88 ff ff ff
page canvas
cls 2178
xstr 150,170,500,50,13,61310,2178,1,1,1,"QIDI Plus 4"
xstr 150,232,500,34,8,36020,2178,1,1,1,"Starting up..."
```
The screen therefore boots at 921600 baud (QIDI's firmware boots at 115200). The last three lines are a power-on splash (Theme.BG, TEXT and MUTED as RGB565) that stays until klipmi draws its first frame.

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
Pictures have no alpha, so every icon strip is baked for one (ink, backdrop) pair and every corner sheet for one (fill, backdrop) pair, all from `Theme` (`src/klipmi/canvas/gfx.py`). `assets/pics/pics.json` lists them in id order (`order`).

Icon strips: 66 icons, 25 per row, cell = icon size (`xpic x,y,s,s,(n%25)*s,(n//25)*s,id`), icon order in `ICON_NAMES` and `tools/hmi_assets.js`.

| ids (24 px) | ids (32 px) | ink on backdrop |
|---|---|---|
| 0 | 10 | MUTED on BG |
| 1 | 11 | TEXT on BG |
| 2 | 12 | ACCENT on SURFACE |
| 3 | 13 | MUTED on SURFACE |
| 4 | 14 | TEXT on SURFACE |
| 5 | 15 | OK on SURFACE |
| 6 | 16 | MUTED on SURFACE2 |
| 7 | 17 | TEXT on SURFACE2 |
| 8 | 18 | BG on ACCENT |
| 9 | 19 | ERR_INK on ERR_DIM |

Picture 20 is the corner atlas: 24 sheets of 96x100 px, 8 per row, in `CORNER_PAIRS` order. In a sheet, radii 4, 6, 8, 10, 12, 16, 20, 24 are stacked top to bottom (y 0, 4, 10, 18, 28, 40, 56, 76) and the four r x r corners sit side by side at x = k*r (top-left, top-right, bottom-left, bottom-right).

Adding or reordering pictures renumbers the ids: keep this table, `pics.json` and `gfx.py` in step. To import them in order, copy the PNGs to a folder with numbered names (`00_ic24_muted_bg.png` and so on) and add them one at a time: the editor's open dialog cannot take all 21 names at once.

## Rebuild
1. `node tools/hmi_assets.js` (only if icons or palette changed), delete the pictures in the editor's picture list, re-add them one at a time in the id order above.
2. Compile (toolbar), File > "output production file" with the folder set to this directory.
3. Flash: `.venv/bin/python tools/flash_tft.py --baud 921600 hmi/plus4-canvas/plus4-canvas.tft` on the printer (this firmware boots at 921600; a screen still on QIDI firmware that was not driven by klipmi answers at 115200, so use `--baud 115200 --upload-baud 921600`).

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
