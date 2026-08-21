from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
CORE_ROOT = ROOT.parent
PATHS = [
    ROOT / "src",
    ROOT / "tests",
    CORE_ROOT / "dwlabbasicpy" / "src",
    CORE_ROOT / "dwlabbackup" / "src",
]

for path in PATHS:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)
