"""
Root test runner entrypoint.
Executes the comprehensive Dot tool test suite in backend/tests/.
"""

import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
RUNNER = ROOT_DIR / "backend" / "tests" / "run_all_tests.py"

if __name__ == "__main__":
    # Locate the virtual environment executable.
    venv_py = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        py_exe = str(venv_py)
    else:
        py_exe = sys.executable

    ret = subprocess.run([py_exe, str(RUNNER)])
    sys.exit(ret.returncode)

