"""The bot's modules import each other by plain name (src/ is on sys.path when main.py runs)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
