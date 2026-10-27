# QIDI Plus 4 HMI

The UI this service drives is QIDI's stock Plus 4 screen project, published under AGPL-3.0:

- `UI/xindi_800_480.HMI` (editable project, open with the TJC USART HMI editor)
- `UI/xindi_800_480.tft` (compiled, what the screen runs)

from <https://github.com/QIDITECH/QIDI_PLUS4> (v1.7.1 when this was written). Screen: TJC8048X250_011C, 800x480, 32 MB flash.

The files are not committed here (56 MB). Download them into this folder as-is; klipmi addresses pages by name (`page one_box_page`) because page indices are not stable across editor saves.

Pages used so far: `logo` (boot), `main`, `one_box_page`, `zero_box_page`. Component maps are in `docs/plus4-hmi.md`.
