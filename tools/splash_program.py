#!/usr/bin/env python3
"""Print the screen firmware's power-on splash, for the canvas page's post-initialize event in the HMI editor.

    PYTHONPATH=src python tools/splash_program.py
"""

from klipmi.canvas.splash import firmware_program

if __name__ == "__main__":
    print("\n".join(firmware_program()))
