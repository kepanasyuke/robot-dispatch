#!/usr/bin/env python
"""Render the dispatch scenario as an animated GIF.

The animation tells the reliability story in one loop: a task is queued, a robot
takes it, the robot goes silent, the lease expires, the task is retried on a
second robot and succeeds. Frames are drawn with Pillow so the file is
reproducible from the repository (`python scripts/dev.py docs`).

Usage:
    python scripts/make_animation.py
    python scripts/make_animation.py --png-dir .tmp/frames   # export frames for review
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs" / "animation" / "dispatch-flow.gif"

WIDTH, HEIGHT = 960, 540

COLORS = {
    "bg": "#0b1220",
    "panel": "#111a2e",
    "panel_border": "#22304a",
    "card": "#0f1830",
    "card_border": "#25344e",
    "text": "#e9f0fb",
    "muted": "#8ea3c4",
    "mono": "#93a8c8",
    "line": "#40608f",
    "pending": "#94a3b8",
    "assigned": "#60a5fa",
    "running": "#34d399",
    "retrying": "#fbbf24",
    "succeeded": "#22c55e",
    "failed": "#f87171",
    "danger": "#f87171",
}

FONT_CANDIDATES = {
    "regular": [
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "bold": [
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "mono": [
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ],
}


def load_font(kind: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES[kind]:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


@dataclass(frozen=True)
class Frame:
    caption: str
    detail: str
    status: str
    attempts: int
    progress: int
    lease: str
    robot1: str = "idle"
    robot2: str = "idle"
    hot: tuple[str, ...] = field(default_factory=tuple)


FRAMES: tuple[Frame, ...] = (
    Frame(
        caption="1 · Заказчик ставит задачу",
        detail="POST /api/v1/tasks · Idempotency-Key: wms:A-100 · priority 200",
        status="pending",
        attempts=0,
        progress=0,
        lease="—",
        hot=("wms_api",),
    ),
    Frame(
        caption="2 · Диспетчер забирает задачу из очереди",
        detail="SELECT … FOR UPDATE SKIP LOCKED · два диспетчера не возьмут одну задачу",
        status="pending",
        attempts=0,
        progress=0,
        lease="—",
        hot=("api_disp",),
    ),
    Frame(
        caption="3 · Назначение и команда через outbox",
        detail="robot-1 · command_id 4f2a… · attempt 1/3 · задача, робот и команда — одна транзакция",
        status="assigned",
        attempts=1,
        progress=0,
        lease="00:30",
        robot1="busy",
        hot=("disp_mq", "mq_robot1"),
    ),
    Frame(
        caption="4 · Робот шлёт прогресс — lease продлевается",
        detail="progress 65% · lease +30 c · команда не считается зависшей",
        status="running",
        attempts=1,
        progress=65,
        lease="00:30",
        robot1="busy",
        hot=("mq_robot1",),
    ),
    Frame(
        caption="5 · Робот замолчал",
        detail="нет heartbeat 30 c · lease истекает · результат не придёт",
        status="running",
        attempts=1,
        progress=65,
        lease="00:00",
        robot1="dead",
    ),
    Frame(
        caption="6 · Lease истёк — повторная постановка",
        detail="attempt 2/3 · backoff 5 c · last_error: lease expired · робот освобождён",
        status="retrying",
        attempts=2,
        progress=0,
        lease="—",
        robot1="dead",
        hot=("disp_mq",),
    ),
    Frame(
        caption="7 · Второй робот берёт задачу",
        detail="robot-2 · новый command_id · attempt 2/3 · повтор безопасен по контракту",
        status="running",
        attempts=2,
        progress=40,
        lease="00:30",
        robot2="busy",
        hot=("mq_robot2",),
    ),
    Frame(
        caption="8 · Успех — роботы свободны",
        detail="result: delivered · 2 попытки · задача закрыта, флот снова idle",
        status="succeeded",
        attempts=2,
        progress=100,
        lease="—",
    ),
)


def rounded(draw: ImageDraw.ImageDraw, box, radius: int, fill: str, outline: str, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font,
    fill: str,
    anchor: str = "la",
) -> None:
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str,
    width: int,
) -> None:
    draw.line([start, end], fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head = 9
    left = (end[0] - head * math.cos(angle - 0.45), end[1] - head * math.sin(angle - 0.45))
    right = (end[0] - head * math.cos(angle + 0.45), end[1] - head * math.sin(angle + 0.45))
    draw.polygon([end, left, right], fill=color)


def pill(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, color: str, font) -> None:
    padding = 14
    width = draw.textlength(text, font=font) + padding * 2
    height = 34
    draw.rounded_rectangle(
        (x - width, y, x, y + height),
        radius=height // 2,
        fill="#0d1526",
        outline=color,
        width=2,
    )
    draw.text((x - width / 2, y + height / 2), text, font=font, fill=color, anchor="mm")


def robot_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    name: str,
    state: str,
    font_bold,
    font_mono,
) -> None:
    palette = {
        "idle": COLORS["panel_border"],
        "busy": COLORS["running"],
        "dead": COLORS["danger"],
    }
    status_text = {"idle": "idle", "busy": "выполняет", "dead": "timeout"}[state]
    fill = COLORS["panel"] if state != "dead" else "#241521"
    rounded(draw, box, 12, fill, palette[state], width=3 if state != "idle" else 2)
    x, y, _, _ = box
    label(draw, (x + 12, y + 12), name, font_bold, COLORS["text"])
    status_color = {
        "idle": COLORS["muted"],
        "busy": COLORS["running"],
        "dead": COLORS["danger"],
    }[state]
    label(draw, (x + 12, y + 36), status_text, font_mono, status_color)
    if state == "dead":
        draw.line((box[2] - 18, y + 12, box[2] - 8, y + 22), fill=COLORS["danger"], width=3)
        draw.line((box[2] - 8, y + 12, box[2] - 18, y + 22), fill=COLORS["danger"], width=3)


def render(frame: Frame, index: int, total: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg"])
    draw = ImageDraw.Draw(image)

    bold = load_font("bold", 15)
    bold_small = load_font("bold", 13)
    bold_big = load_font("bold", 21)
    regular = load_font("regular", 13)
    mono = load_font("mono", 12)
    mono_small = load_font("mono", 11)

    label(draw, (32, 26), "Сценарий диспетчеризации", bold_big, COLORS["text"])
    label(
        draw,
        (32, 56),
        "задача, молчащий робот и повтор на другом роботе",
        regular,
        COLORS["muted"],
    )

    # ---------------------------------------------------------------- topology
    hot = set(frame.hot)
    hot_color = COLORS["running"]
    idle_color = COLORS["line"]

    components = [
        ("WMS", (32, 96, 172, 166)),
        ("API · FastAPI", (196, 96, 366, 166)),
        ("Dispatcher", (386, 96, 556, 166)),
        ("RabbitMQ", (576, 96, 716, 166)),
    ]
    active_components = {
        "wms_api": {"WMS", "API · FastAPI"},
        "api_disp": {"API · FastAPI", "Dispatcher"},
        "disp_mq": {"Dispatcher", "RabbitMQ"},
        "mq_robot1": {"RabbitMQ", "robot-1"},
        "mq_robot2": {"RabbitMQ", "robot-2"},
    }
    highlighted: set[str] = set()
    for key in hot:
        highlighted |= active_components.get(key, set())

    for name, box in components:
        is_hot = name in highlighted
        rounded(
            draw,
            box,
            12,
            "#0f2033" if is_hot else COLORS["panel"],
            hot_color if is_hot else COLORS["panel_border"],
            width=3 if is_hot else 2,
        )
        label(draw, (box[0] + 12, box[1] + 12), name, bold_small, COLORS["text"])
        subtitle = {
            "WMS": "HTTP",
            "API · FastAPI": "/api/v1",
            "Dispatcher": "SKIP LOCKED",
            "RabbitMQ": "AMQP",
        }[name]
        label(draw, (box[0] + 12, box[1] + 36), subtitle, mono_small, COLORS["muted"])

    robot_card(draw, (760, 78, 900, 138), "robot-1", frame.robot1, bold_small, mono_small)
    robot_card(draw, (760, 150, 900, 210), "robot-2", frame.robot2, bold_small, mono_small)

    edges = {
        "wms_api": ((172, 131), (196, 131)),
        "api_disp": ((366, 131), (386, 131)),
        "disp_mq": ((556, 131), (576, 131)),
        "mq_robot1": ((716, 128), (760, 108)),
        "mq_robot2": ((716, 140), (760, 180)),
    }
    for key, (start, end) in edges.items():
        is_hot = key in hot
        if key in {"mq_robot1", "mq_robot2"}:
            active = frame.robot1 if key == "mq_robot1" else frame.robot2
            if active == "idle" and not is_hot:
                continue
        arrow(draw, start, end, hot_color if is_hot else idle_color, 3 if is_hot else 2)

    # ------------------------------------------------------------------- card
    rounded(draw, (32, 232, 928, 420), 16, COLORS["card"], COLORS["card_border"], width=2)
    label(draw, (52, 252), "task 9f3c-4d1a", mono, COLORS["text"])
    label(draw, (52, 274), "delivery · priority 200 · wms:A-100", mono_small, COLORS["mono"])

    status_color = COLORS.get(frame.status, COLORS["muted"])
    pill(draw, 908, 248, frame.status, status_color, mono)

    # attempts
    attempts_text = f"attempt {frame.attempts}/3" if frame.attempts else "attempt 0/3"
    label(draw, (52, 312), attempts_text, mono, COLORS["mono"])
    for dot in range(3):
        cx = 190 + dot * 26
        cy = 320
        filled = dot < frame.attempts
        draw.ellipse(
            (cx - 7, cy - 7, cx + 7, cy + 7),
            fill=status_color if filled else "#1b2740",
            outline=COLORS["card_border"],
            width=1,
        )

    # progress
    bar_x, bar_y, bar_w, bar_h = 52, 350, 700, 18
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=9, fill="#16213a")
    if frame.progress > 0:
        draw.rounded_rectangle(
            (bar_x, bar_y, bar_x + bar_w * frame.progress / 100, bar_y + bar_h),
            radius=9,
            fill=status_color,
        )
    label(draw, (bar_x + bar_w + 16, bar_y - 2), f"{frame.progress}%", mono, COLORS["mono"])

    # lease + detail
    lease_color = COLORS["danger"] if frame.lease == "00:00" else COLORS["mono"]
    label(draw, (52, 384), f"lease {frame.lease}", mono_small, lease_color)
    label(draw, (190, 384), "command_id 4f2a-9c11", mono_small, COLORS["mono"])

    # ---------------------------------------------------------------- caption
    label(draw, (32, 448), frame.caption, bold, COLORS["text"])
    label(draw, (32, 474), frame.detail, regular, COLORS["muted"])

    # timeline dots
    for dot in range(total):
        cx = 780 + dot * 20
        cy = 510
        active = dot == index
        draw.ellipse(
            (cx - 4, cy - 4, cx + 4, cy + 4),
            fill=status_color if active else "#243250",
        )

    footer = "robot-dispatch · lifecycle: pending → assigned → running → retrying → succeeded"
    label(draw, (32, 506), footer, mono_small, "#5f7396")
    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the dispatch scenario GIF")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--png-dir", type=Path, default=None, help="also export frames as PNG")
    parser.add_argument("--duration-ms", type=int, default=1200)
    args = parser.parse_args(argv)

    images = [render(frame, index, len(FRAMES)) for index, frame in enumerate(FRAMES)]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        args.out,
        save_all=True,
        append_images=images[1:],
        duration=args.duration_ms,
        loop=0,
        optimize=True,
    )

    if args.png_dir is not None:
        args.png_dir.mkdir(parents=True, exist_ok=True)
        for index, image in enumerate(images):
            image.save(args.png_dir / f"frame-{index + 1:02d}.png")

    size_kb = args.out.stat().st_size / 1024
    print(f"wrote {args.out.relative_to(ROOT)} ({len(images)} frames, {size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
