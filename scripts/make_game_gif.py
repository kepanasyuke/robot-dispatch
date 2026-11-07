#!/usr/bin/env python
"""Render the gameplay GIF for the README.

The game renders a deterministic mid-game frame for `?embed=1&demo=<seconds>&freeze=1`,
so a sequence of headless-browser screenshots becomes an animation of a real
play session: the cleaning robot chases stains, foam flies, deadlines tick.

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


def capture(browser: str, moment: float, destination: Path, profile: Path) -> Image.Image:
    url = f"{GAME.as_uri()}?embed=1&freeze=1&demo={moment}"
    base = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        f"--window-size={WIDTH},{HEIGHT}",
        "--virtual-time-budget=2000",
    ]
    last_error: subprocess.CalledProcessError | None = None
    for _ in range(3):
        try:
            subprocess.run(
                [*base, f"--screenshot={destination}", url],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            last_error = None
            break
        except subprocess.CalledProcessError as error:
            last_error = error
    if last_error is not None:
        raise last_error
    image = Image.open(destination).convert("RGB")
    if image.size != (WIDTH, HEIGHT):
        image = image.crop((0, 0, WIDTH, HEIGHT))
    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render docs/game/gameplay.gif")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--duration-ms", type=int, default=380)
    parser.add_argument("--colors", type=int, default=200, help="palette size; 0 keeps true color")
    parser.add_argument(
        "--width", type=int, default=880, help="output width in pixels; 0 keeps the capture size"
    )
    args = parser.parse_args(argv)

    browser = find_browser()
    frames: list[Image.Image] = []
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "profile"
        profile.mkdir()
        for index, moment in enumerate(FRAME_TIMES):
            frame_path = Path(tmp) / f"frame-{index:02d}.png"
            frames.append(capture(browser, moment, frame_path, profile))
            print(f"  captured t={moment:.1f}s")

    if args.width and args.width != WIDTH:
        height = round(HEIGHT * args.width / WIDTH)
        frames = [frame.resize((args.width, height), Image.LANCZOS) for frame in frames]

    if args.colors:
        base = frames[0].quantize(colors=args.colors, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
        frames = [base] + [frame.quantize(palette=base, dither=Image.Dither.NONE) for frame in frames[1:]]

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
    try:
        shown = args.out.resolve().relative_to(ROOT)
    except ValueError:
        shown = args.out
    print(f"wrote {shown} ({len(frames)} frames, {size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
