"""Bake the data snapshot into the static dashboard template -> a self-contained
HTML page suitable for publishing as a shareable Artifact (no backend needed).
"""
from __future__ import annotations

import json

from src import config
from scripts.export_snapshot import main as export_snapshot

TEMPLATE = config.PROJECT_ROOT / "dashboard" / "static" / "index.html"
OUT = config.PROJECT_ROOT / "reports" / "dashboard.html"


def main() -> int:
    export_snapshot()
    snapshot = json.loads((config.PROJECT_ROOT / "reports" / "snapshot.json").read_text())
    html = TEMPLATE.read_text()
    start, end = html.index("/*DATA*/"), html.index("/*DATA*/", html.index("/*DATA*/") + 1)
    baked = html[:start] + "/*DATA*/" + json.dumps(snapshot) + html[end:]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(baked)
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
