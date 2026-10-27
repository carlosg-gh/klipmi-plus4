# plus4-canvas HMI project

Our own minimal TJC project for the Plus 4 screen (TJC8048X250_011, 800x480). One blank page `canvas`, no timers, no touch components: Python draws everything (`src/klipmi/canvas/`). Built with the TJC "USART HMI" editor 1.68.2.

- `plus4-canvas.HMI`: editor project (encoding utf-8, orientation 0)
- `plus4-canvas.tft`: compiled firmware (0.5 MB: pictures 73,659 B, fonts 30,710 B, no errors or warnings)
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

Adding or reordering pictures renumbers the ids: keep this table, `assets/pics/pics.json` and the canvas code in step.

## Rebuild
1. `node tools/hmi_assets.js` (only if icons or palette changed), delete the pictures in the editor's picture list, re-add them one at a time in the id order above.
2. Compile (toolbar), File > "output production file" with the folder set to this directory.
3. Flash: `~/klipmi/venv/bin/python ~/klipmi/flash_tft.py --baud 115200 --upload-baud 921600 plus4-canvas.tft` on the printer (screen must be at the baud given by `--baud`).
