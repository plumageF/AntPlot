from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = os.environ.copy()
    env.setdefault("ANTPLOT_HOST", "0.0.0.0")
    env.setdefault("ANTPLOT_PORT", "8765")

    backend = subprocess.Popen(
        [sys.executable, "-m", "src.hfss_paperplotter.preview_server"],
        cwd=ROOT,
        env=env,
    )
    frontend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            "4173",
            "--bind",
            "0.0.0.0",
            "--directory",
            str(ROOT / "frontend" / "dist"),
        ],
        cwd=ROOT,
        env=env,
    )
    print("AntPlot is available at http://127.0.0.1:4173")

    try:
        while True:
            backend_code = backend.poll()
            frontend_code = frontend.poll()
            if backend_code is not None:
                frontend.terminate()
                return backend_code
            if frontend_code is not None:
                backend.terminate()
                return frontend_code
            time.sleep(1)
    except KeyboardInterrupt:
        backend.terminate()
        frontend.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
