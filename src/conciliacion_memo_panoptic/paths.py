import sys
from pathlib import Path


def _resolve_root() -> Path:
    # Cuando corre como .exe compilado (PyInstaller), usar la carpeta del exe.
    # Cuando corre como script Python, usar la raíz del proyecto.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _resolve_root()
