"""Build/run the frontend with node_modules kept OFF the Google Drive mount.

The repo lives on Google Drive, whose filesystem breaks `npm install` and
won't allow links to local disk. So npm, TypeScript and Vite run from a local
toolchain directory, pointed at the source in this folder; only the small
`dist/` build output is written back here (gitignored, served by FastAPI).

    python frontend/toolchain.py install   # (re)install node_modules locally; run after editing package.json
    python frontend/toolchain.py check     # TypeScript type-check only
    python frontend/toolchain.py build     # type-check + production build -> frontend/dist
    python frontend/toolchain.py dev       # Vite dev server on :5173, proxying /api to :8000
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
# Under the home dir rather than %LOCALAPPDATA%: packaged desktop apps get a
# virtualized LOCALAPPDATA, which would hide one shell's install from another.
TOOL = Path(os.environ.get("VOL_FITTER_FRONTEND_TOOLCHAIN", Path.home() / ".vol_fitter" / "frontend-toolchain"))
NM = TOOL / "node_modules"
DIST = SRC / "dist"
STAMP = TOOL / ".package-hash"

VITE_CONFIG = """\
import {{ defineConfig }} from "vite";
import react from "@vitejs/plugin-react";

const SRC = {src};
const NM = {nm};
const DEPS = {deps};
const esc = (s) => s.replace(/[.*+?^${{}}()|[\\]\\\\]/g, "\\\\$&");

// Source lives on a filesystem with no node_modules, so map every runtime
// dependency (and its subpaths, e.g. react/jsx-runtime) to the local install.
export default defineConfig({{
  root: SRC,
  base: "./",  // relative asset URLs, so the build also works behind a path-prefixed proxy
  cacheDir: {cache},
  plugins: [react()],
  resolve: {{
    alias: DEPS.map((d) => ({{ find: new RegExp("^" + esc(d) + "(/.*)?$"), replacement: NM + "/" + d + "$1" }})),
  }},
  server: {{
    port: 5173,
    strictPort: true,
    proxy: {{ "/api": "http://localhost:8000" }},
    fs: {{ allow: [SRC, NM] }},
  }},
  build: {{ outDir: {dist}, emptyOutDir: true, chunkSizeWarningLimit: 5000 }},
}});
"""


def _tsconfig() -> dict:
    return {
        "compilerOptions": {
            "target": "ES2020", "lib": ["ES2020", "DOM", "DOM.Iterable"],
            "module": "ESNext", "moduleResolution": "bundler", "jsx": "react-jsx",
            "strict": True, "noUnusedLocals": True, "noUnusedParameters": True,
            "skipLibCheck": True, "isolatedModules": True, "noEmit": True,
            # @types first: otherwise a package's plain .js file (react/jsx-runtime.js) wins and has no types.
            "baseUrl": ".", "paths": {"*": ["node_modules/@types/*", "node_modules/*"]},
            "types": ["vite/client"],
        },
        "include": [(SRC / "src").as_posix()],
    }


def _package_hash() -> str:
    h = hashlib.sha256((SRC / "package.json").read_bytes())
    lock = SRC / "package-lock.json"
    if lock.exists():
        h.update(lock.read_bytes())
    return h.hexdigest()


def _npm() -> str:
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("npm not found on PATH -- install Node.js first.")
    return npm


def install(force: bool = False) -> None:
    TOOL.mkdir(parents=True, exist_ok=True)
    if not force and NM.is_dir() and STAMP.exists() and STAMP.read_text() == _package_hash():
        return
    shutil.copy2(SRC / "package.json", TOOL / "package.json")
    lock = SRC / "package-lock.json"
    if lock.exists():
        shutil.copy2(lock, TOOL / "package-lock.json")
    subprocess.run([_npm(), "install"], cwd=TOOL, check=True)
    shutil.copy2(TOOL / "package-lock.json", lock)  # keep the lockfile versioned in the repo
    STAMP.write_text(_package_hash())


def _write_configs() -> None:
    deps = list(json.loads((SRC / "package.json").read_text())["dependencies"])
    (TOOL / "vite.config.mjs").write_text(VITE_CONFIG.format(
        src=json.dumps(SRC.as_posix()), nm=json.dumps(NM.as_posix()), deps=json.dumps(deps),
        cache=json.dumps((TOOL / ".vite").as_posix()), dist=json.dumps(DIST.as_posix()),
    ))
    (TOOL / "tsconfig.json").write_text(json.dumps(_tsconfig(), indent=2))


def _node(*args: str) -> None:
    subprocess.run(["node", *args], cwd=TOOL, check=True)


def check() -> None:
    _node(str(NM / "typescript" / "bin" / "tsc"), "-p", "tsconfig.json")


def build() -> None:
    check()
    _node(str(NM / "vite" / "bin" / "vite.js"), "build", "--config", "vite.config.mjs")


def dev() -> None:
    _node(str(NM / "vite" / "bin" / "vite.js"), "--config", "vite.config.mjs")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd not in {"install", "check", "build", "dev"}:
        sys.exit(__doc__)
    install(force=(cmd == "install"))
    _write_configs()
    {"install": lambda: None, "check": check, "build": build, "dev": dev}[cmd]()
