"""Render kvmchaos run records to a self-contained HTML report.

Reads every ``*.json`` file under a runs directory (one record per file,
produced by the ``inject`` command) and renders a static HTML page with a
summary header and a sortable table of runs.

Pure stdlib: no Jinja, no CSS framework, no JavaScript.
"""

from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

_COLUMNS: tuple[str, ...] = (
    "started_at",
    "fault",
    "vm",
    "outcome",
    "duration_s",
    "dry_run",
)


def load_records(runs_dir: Path) -> list[dict[str, object]]:
    """Load every well-formed run record under ``runs_dir``, newest first.

    Args:
        runs_dir: Directory containing per-run ``*.json`` files.

    Returns:
        List of record dicts sorted by ``started_at`` descending. Missing
        directory, non-JSON files, and unparsable JSON are skipped silently.
    """
    if not runs_dir.is_dir():
        return []
    records: list[dict[str, object]] = []
    for path in runs_dir.glob("*.json"):
        try:
            records.append(json.loads(path.read_text()))
        except OSError, json.JSONDecodeError:
            continue
    records.sort(key=lambda r: str(r.get("started_at", "")), reverse=True)
    return records


def render_html(records: list[dict[str, object]]) -> str:
    """Render a list of run records as a self-contained HTML document.

    Args:
        records: Run record dicts, any order.

    Returns:
        A complete HTML string (``<!doctype html>`` through ``</html>``).
    """
    if not records:
        return _page("kvmchaos report", "<p>No runs recorded.</p>")
    body = _summary(records) + _table(records)
    return _page("kvmchaos report", body)


def generate(output: Path, runs_dir: Path) -> Path:
    """Load records and write the rendered HTML to ``output``.

    Creates the output parent directory if needed.

    Args:
        output: Target HTML file path.
        runs_dir: Directory containing run records.

    Returns:
        The ``output`` path, for the caller's convenience.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(load_records(runs_dir)))
    return output


def _summary(records: list[dict[str, object]]) -> str:
    """Render the top summary block (total, per-outcome counts, date range)."""
    counts = Counter(str(r.get("outcome", "unknown")) for r in records)
    start = min(str(r.get("started_at", "")) for r in records)
    end = max(str(r.get("ended_at", "")) for r in records)
    parts = [
        f"<p>Total: {len(records)}</p>",
        "<ul>"
        + "".join(
            f"<li>{html.escape(outcome)}: {count}</li>" for outcome, count in sorted(counts.items())
        )
        + "</ul>",
        f"<p>Range: {html.escape(_fmt_ts(start))} → {html.escape(_fmt_ts(end))}</p>",
    ]
    return "<section><h2>Summary</h2>" + "".join(parts) + "</section>"


def _table(records: list[dict[str, object]]) -> str:
    """Render the per-run table with expandable step details."""
    header = "<tr>" + "".join(f"<th>{col}</th>" for col in _COLUMNS) + "<th>steps</th></tr>"
    rows = [_row(r) for r in records]
    return "<section><h2>Runs</h2><table>" + header + "".join(rows) + "</table></section>"


def _row(record: dict[str, object]) -> str:
    """Render one table row including an expandable steps pane."""
    cells = "".join(
        f"<td>{html.escape(_display(col, record.get(col, '')))}</td>" for col in _COLUMNS
    )
    steps_json = json.dumps(record.get("steps", []), indent=2)
    details = (
        f"<td><details><summary>show</summary><pre>{html.escape(steps_json)}</pre></details></td>"
    )
    return "<tr>" + cells + details + "</tr>"


def _display(column: str, value: object) -> str:
    """Format a cell value for human display.

    ISO 8601 timestamps are re-formatted via :func:`_fmt_ts`. Other columns
    pass through as ``str(value)``.
    """
    text = str(value)
    if column == "started_at":
        return _fmt_ts(text)
    return text


def _fmt_ts(iso: str) -> str:
    """Re-format a UTC ISO 8601 timestamp for readability.

    ``2026-04-22T22:03:14+00:00`` becomes ``2026-04-22 | 22:03:14 UTC``.
    Non-UTC or non-conforming strings pass through unchanged.
    """
    if not iso.endswith("+00:00"):
        return iso
    naive = iso[: -len("+00:00")]
    date_part, _, time_part = naive.partition("T")
    if not time_part:
        return iso
    return f"{date_part} | {time_part} UTC"


def _page(title: str, body: str) -> str:
    """Wrap ``body`` in a minimal HTML skeleton with inline CSS."""
    css = (
        "body{font-family:sans-serif;margin:2em auto;max-width:1100px}"
        "table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ccc;padding:4px 8px;text-align:left;"
        "vertical-align:top}"
        "th{background:#eee}"
        "pre{margin:0;font-size:0.9em}"
        "details summary{cursor:pointer;color:#06c}"
    )
    escaped_title = html.escape(title)
    return (
        "<!doctype html>"
        f"<html><head><meta charset='utf-8'><title>{escaped_title}</title>"
        f"<style>{css}</style></head>"
        f"<body><h1>{escaped_title}</h1>{body}</body></html>"
    )
