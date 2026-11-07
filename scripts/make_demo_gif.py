from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "docs" / "frames"
OUTPUT = ROOT / "docs" / "demo.gif"
WIDTH = 880
COLORS = 96
DURATION_MS = 550


def load_frames() -> list[Image.Image]:
    files = sorted(FRAMES.glob("frame-*.png"))
    if not files:
        raise SystemExit("нет кадров: сначала запустите `npx playwright test e2e/docs.spec.ts`")
    frames: list[Image.Image] = []
    for file in files:
        image = Image.open(file).convert("RGB")
        ratio = WIDTH / image.width
        height = int(round(image.height * ratio))
        resized = image.resize((WIDTH, height), Image.LANCZOS)
        frames.append(resized.convert("P", palette=Image.ADAPTIVE, colors=COLORS))
    return frames


def main() -> int:
    frames = load_frames()
    width = max(frame.width for frame in frames)
    height = max(frame.height for frame in frames)
    normalized = [
        frame if frame.size == (width, height) else frame.resize((width, height), Image.LANCZOS)
        for frame in frames
    ]
    normalized[0].save(
        OUTPUT,
        save_all=True,
        append_images=normalized[1:],
        duration=DURATION_MS,
        loop=0,
        optimize=True,
    )
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"{OUTPUT.relative_to(ROOT)}: {len(normalized)} кадров, {width}x{height}, {size_kb:.0f} КБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
