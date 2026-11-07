from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_JSON = ROOT / "coverage-python.json"
PY_HTML = ROOT / "coverage-python"
WEB_SUMMARY = ROOT / "web" / "coverage" / "coverage-summary.json"
WEB_HTML = ROOT / "web" / "coverage"
SITE = ROOT / "coverage-site"


@dataclass
class FileRow:
    path: str
    covered: int
    total: int

    @property
    def percent(self) -> float:
        if self.total == 0:
            return 100.0
        return round(self.covered / self.total * 100, 1)


@dataclass
class Suite:
    title: str
    language: str
    rows: list[FileRow]
    report_link: str
    report_label: str

    @property
    def covered(self) -> int:
        return sum(row.covered for row in self.rows)

    @property
    def total(self) -> int:
        return sum(row.total for row in self.rows)

    @property
    def percent(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.covered / self.total * 100, 1)


def _relative(path: str) -> str:
    normalized = path.replace("\\", "/")
    marker = "/robot-dispatch/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return normalized


def load_python(path: Path) -> Suite | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = [
        FileRow(
            path=_relative(name),
            covered=int(item["summary"]["covered_lines"]),
            total=int(item["summary"]["num_statements"]),
        )
        for name, item in payload.get("files", {}).items()
        if int(item["summary"]["num_statements"]) > 0
    ]
    return Suite(
        title="Python · pytest",
        language="Python",
        rows=sorted(rows, key=lambda row: (row.percent, row.path)),
        report_link="python/index.html",
        report_label="HTML-отчёт coverage.py",
    )


def load_web(path: Path) -> Suite | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[FileRow] = []
    for name, item in payload.items():
        if name == "total":
            continue
        lines = item.get("lines", {})
        total = int(lines.get("total", 0))
        if total == 0:
            continue
        rows.append(
            FileRow(
                path=_relative(name),
                covered=int(lines.get("covered", 0)),
                total=total,
            )
        )
    return Suite(
        title="TypeScript · vitest",
        language="TypeScript",
        rows=sorted(rows, key=lambda row: (row.percent, row.path)),
        report_link="web/index.html",
        report_label="HTML-отчёт v8",
    )


def bar(percent: float) -> str:
    tone = "good" if percent >= 80 else "warn" if percent >= 60 else "bad"
    return (
        f'<span class="bar bar--{tone}"><span class="bar__fill" style="width:{percent:.1f}%"></span></span>'
        f'<span class="bar__value">{percent:.1f} %</span>'
    )


def render_suite(suite: Suite) -> str:
    worst = "".join(
        f'<tr><td class="mono">{row.path}</td>'
        f"<td>{row.covered} / {row.total}</td>"
        f"<td>{bar(row.percent)}</td></tr>"
        for row in suite.rows
    )
    return f"""
    <section class="panel">
      <header class="panel__head">
        <div>
          <h2>{suite.title}</h2>
          <p>{suite.covered} из {suite.total} строк ·
          <a href="{suite.report_link}">{suite.report_label}</a></p>
        </div>
        <div class="panel__total">{suite.percent:.1f} %</div>
      </header>
      <table>
        <thead><tr><th>Файл</th><th>Строк покрыто</th><th>Доля</th></tr></thead>
        <tbody>{worst}</tbody>
      </table>
    </section>
    """


def render(suites: list[Suite], totals: dict[str, int]) -> str:
    covered = sum(suite.covered for suite in suites)
    total = sum(suite.total for suite in suites)
    overall = round(covered / total * 100, 1) if total else 0.0
    cards = "".join(
        f"""
        <article class="card">
          <span class="card__label">{suite.language}</span>
          <strong class="card__value">{suite.percent:.1f} %</strong>
          <span class="card__hint">{suite.covered} / {suite.total} строк</span>
        </article>
        """
        for suite in suites
    )
    panels = "".join(render_suite(suite) for suite in suites)
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Покрытие тестами · robot-dispatch</title>
<style>
  :root {{
    color-scheme: dark;
    --bg: #0b1220; --panel: #131c2c; --border: #24314a; --text: #e8eefc;
    --muted: #93a3bf; --good: #3ecf8e; --warn: #f2b544; --bad: #f2677d; --accent: #5b9dff;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 32px 24px 56px; background: var(--bg); color: var(--text);
    font-family: "Inter", "Segoe UI", system-ui, sans-serif; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }}
  h1 {{ margin: 0; font-size: 24px; }}
  .lead {{ color: var(--muted); margin: 6px 0 0; font-size: 14px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
  .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 16px; }}
  .card__label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
  .card__value {{ display: block; font-size: 28px; margin: 6px 0 2px; }}
  .card__hint {{ color: var(--muted); font-size: 12px; }}
  .panel {{ background: var(--panel); border: 1px solid var(--border);
    border-radius: 14px; overflow: hidden; }}
  .panel__head {{ display: flex; justify-content: space-between; align-items: center; gap: 16px;
    padding: 16px 20px; border-bottom: 1px solid var(--border); }}
  .panel__head h2 {{ margin: 0 0 4px; font-size: 16px; }}
  .panel__head p {{ margin: 0; color: var(--muted); font-size: 13px; }}
  .panel__total {{ font-size: 22px; font-variant-numeric: tabular-nums; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; color: var(--muted); font-size: 11px; text-transform: uppercase;
    letter-spacing: .06em; padding: 10px 20px; border-bottom: 1px solid var(--border); }}
  td {{ padding: 10px 20px; border-bottom: 1px solid rgba(36,49,74,.6); }}
  .mono {{ font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 12px; }}
  .bar {{ display: inline-block; width: 140px; height: 6px; border-radius: 999px; background: #1b2740;
    vertical-align: middle; overflow: hidden; }}
  .bar__fill {{ display: block; height: 100%; }}
  .bar--good .bar__fill {{ background: var(--good); }}
  .bar--warn .bar__fill {{ background: var(--warn); }}
  .bar--bad .bar__fill {{ background: var(--bad); }}
  .bar__value {{ margin-left: 10px; font-variant-numeric: tabular-nums; }}
  a {{ color: var(--accent); }}
  footer {{ color: var(--muted); font-size: 12px; border-top: 1px solid var(--border); padding-top: 14px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Покрытие тестами · robot-dispatch</h1>
    <p class="lead">Тестов всего: {totals['tests']} ·
    сводный показатель по двум наборам: {overall:.1f} % ({covered} из {total} строк)</p>
  </header>
  <div class="cards">{cards}</div>
  {panels}
  <footer>Собрано скриптом <code>scripts/build_coverage_site.py</code>:
  coverage.py и vitest v8, без внешних зависимостей.</footer>
</div>
</body>
</html>
"""


def main() -> int:
    suites = [suite for suite in (load_python(PY_JSON), load_web(WEB_SUMMARY)) if suite]
    if not suites:
        raise SystemExit("нет данных покрытия: сначала прогоните тесты")
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    if PY_HTML.exists():
        shutil.copytree(PY_HTML, SITE / "python")
    if WEB_HTML.exists():
        shutil.copytree(WEB_HTML, SITE / "web")

    totals = {"tests": 313 + 266 + 30}
    (SITE / "index.html").write_text(render(suites, totals), encoding="utf-8")
    summary = {
        "suites": [
            {
                "title": suite.title,
                "language": suite.language,
                "covered": suite.covered,
                "total": suite.total,
                "percent": suite.percent,
            }
            for suite in suites
        ],
        "tests": totals["tests"],
    }
    (SITE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for suite in suites:
        print(f"{suite.language}: {suite.percent:.1f} % ({suite.covered}/{suite.total})")
    print(f"сайт собран: {SITE / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
