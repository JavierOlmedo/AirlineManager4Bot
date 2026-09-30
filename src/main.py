"""Entry point: ``python src/main.py`` from any working directory."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    # Config, assets and logs are addressed relative to the project root.
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "src"))

    from app import App

    app = App()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.on_close()


if __name__ == "__main__":
    main()
