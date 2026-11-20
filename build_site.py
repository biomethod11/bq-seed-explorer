"""Assemble the Beta Quest Seed Explorer site into site/.

    npm install                 # Pyodide, pinned in package.json
    python build_site.py
    python -m http.server 8000 --directory site

BingoSync's generator files are downloaded from its repository at a pinned commit and
checked against their SHA-256 before use (see THIRD_PARTY.md).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
CACHE = ROOT / ".cache" / "bingosync"
BINGOSYNC = "https://raw.githubusercontent.com/kbuzsaki/bingosync/{commit}/{path}"
BINGOSYNC_COMMIT = "245673501ad6563a7770d2df4393b0a30a3ef62f"
#: site path under sources/ -> (path in BingoSync's repository, first 16 hex of its SHA-256)
BINGOSYNC_FILES = {
    "ocarina_of_time_beta_quest_generator.js": (
        "bingosync-app/generators/ocarina_of_time_beta_quest_generator.js",
        "2bf15564999899e9"
    ),
    "generators/generator_bases/srl_generator_v5_blackout.js": (
        "bingosync-app/generators/generator_bases/srl_generator_v5_blackout.js",
        "c9e6f238dcd5f16c"
    )
}
PAGE_FILES = ("index.html", "styles.css", "app.js", "worker.js", "board.js", "_headers")
PYODIDE_FILES = ('pyodide.mjs', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json')


def bingosync_file(name: str) -> bytes:
    path, digest = BINGOSYNC_FILES[name]
    cached = CACHE / name
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        url = BINGOSYNC.format(commit=BINGOSYNC_COMMIT, path=path)
        with urllib.request.urlopen(url) as response:
            cached.write_bytes(response.read())
    data = cached.read_bytes()
    if hashlib.sha256(data).hexdigest()[:16] != digest:
        cached.unlink()
        raise SystemExit(f"{name} does not match the expected BingoSync file")
    return data


def main() -> int:
    pyodide = ROOT / "node_modules" / "pyodide"
    if not pyodide.is_dir():
        raise SystemExit("run `npm install` first")
    info = json.loads((ROOT / "page" / "build_info.json").read_text(encoding="utf-8"))
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "py").mkdir(parents=True)
    for name in PAGE_FILES:
        shutil.copy2(ROOT / "page" / name, SITE / name)
    sources = {name: bingosync_file(name) for name in BINGOSYNC_FILES}
    for name, data in sources.items():
        (SITE / "sources" / name).parent.mkdir(parents=True, exist_ok=True)
        (SITE / "sources" / name).write_bytes(data)
    (SITE / "pyodide" / info["pyodide_version"]).mkdir(parents=True)
    for name in PYODIDE_FILES:
        shutil.copy2(pyodide / name, SITE / "pyodide" / info["pyodide_version"] / name)
    bundle = SITE / "py" / "betaquest.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted((ROOT / "model").rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(ROOT / "model").as_posix())
        for name, data in sources.items():
            archive.writestr(f"data/sources/{name}", data)
    info["bundle"] = hashlib.sha256(bundle.read_bytes()).hexdigest()[:16]
    (SITE / "build.json").write_text(json.dumps(info) + "\n", encoding="utf-8")
    print(f"built {SITE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
