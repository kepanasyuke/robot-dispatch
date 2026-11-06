#!/usr/bin/env python
"""Render the gameplay GIF for the README.

The game renders a deterministic mid-game frame for `?embed=1&demo=<seconds>`,
so a sequence of headless-browser screenshots becomes an animation of a real
play session: robots carry cubes, orders appear and deadlines tick.

Requires Chrome or Edge (the same engines already used for manual verification).
Usage:
    python scripts/make_game_gif.py
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "docs" / "game" / "index.html"
DEFAULT_OUT = ROOT / "docs" / "game" / "gameplay.gif"

WIDTH, HEIGHT = 960, 480
FRAME_TIMES = (0.6, 1.6, 2.6, 3.6, 4.6, 5.6, 6.6, 7.6, 8.6, 9.6, 10.6, 11.6)

BROWSERS = (
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def find_browser() -> str:
    for candidate in BROWSERS:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("Chrome or Edge is required to render the gameplay GIF")


def capture(browser: str, moment: float, destination: Path) -> Image.Image:
    url = f"{GAME.as_uri()}?embed=1&demo={moment}"
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={WIDTH},{HEIGHT}",
        "--virtual-time-budget=2000",
        f"--screenshot={destination}",
        url,
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    image = Image.open(destination).convert("RGB")
    if image.size != (WIDTH, HEIGHT):
        image = image.crop((0, 0, WIDTH, HEIGHT))
    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render docs/game/gameplay.gif")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--duration-ms", type=int, default=380)
    args = parser.parse_args(argv)

    browser = find_browser()
    frames: list[Image.Image] = []
    with tempfile.TemporaryDirectory() as tmp:
        for index, moment in enumerate(FRAME_TIMES):
            frame_path = Path(tmp) / f"frame-{index:02d}.png"
            frames.append(capture(browser, moment, frame_path))
            print(f"  captured t={moment:.1f}s")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        args.out,
        save_all=True,
        append_images=frames[1:],
        duration=args.duration_ms,
        loop=0,
        optimize=True,
    )
    size_kb = args.out.stat().st_size / 1024
    print(f"wrote {args.out.relative_to(ROOT)} ({len(frames)} frames, {size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
