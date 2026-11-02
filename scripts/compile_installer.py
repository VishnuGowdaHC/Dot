"""
Compile the Inno Setup installer executable for Dot.
This script follows ASD-STE100 standards.
"""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path


def log(message: str) -> None:
    """Print an informational log message."""
    print(f"[INSTALLER BUILDER] {message}")


def log_error(message: str) -> None:
    """Print an error message."""
    print(f"[INSTALLER BUILDER ERROR] {message}", file=sys.stderr)


def find_iscc() -> Path:
    """Locate the Inno Setup compiler executable."""
    which_path = shutil.which("iscc") or shutil.which("ISCC.exe")
    if which_path:
        return Path(which_path)

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")

    candidate_locations = [
        Path(local_app_data) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(local_app_data) / "Programs" / "Inno Setup 7" / "ISCC.exe",
        Path(program_files_x86) / "Inno Setup 6" / "ISCC.exe",
        Path(program_files) / "Inno Setup 6" / "ISCC.exe",
        Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
        Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
    ]

    for cand in candidate_locations:
        if cand.exists():
            return cand

    raise FileNotFoundError("ISCC.exe not found. Please install Inno Setup 6.")


def compute_sha256(file_path: Path) -> str:
    """Compute the SHA256 hexadecimal hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    """Compile the Dot installer."""
    root_dir = Path(__file__).resolve().parent.parent
    iss_file = root_dir / "installer" / "DotSetup.iss"
    output_dir = root_dir / "dist" / "installer"

    if not iss_file.exists():
        log_error(f"Inno Setup script not found: {iss_file}")
        return 1

    dist_app_dir = root_dir / "dist" / "Dot"
    if not dist_app_dir.exists():
        log_error(f"Distribution folder not found: {dist_app_dir}")
        log_error("Run scripts/build_distribution.py first.")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        iscc_path = find_iscc()
        log(f"Using Inno Setup compiler: {iscc_path}")

        log("Compiling installer package with LZMA2 ultra compression...")
        result = subprocess.run(
            [str(iscc_path), str(iss_file)],
            cwd=str(root_dir / "installer"),
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            log_error("ISCC compilation failed:")
            log_error(result.stderr or result.stdout)
            return 1

        installer_exe = output_dir / "Dot-Setup-x64.exe"
        if not installer_exe.exists():
            log_error(f"Expected installer not found: {installer_exe}")
            return 1

        size_mb = installer_exe.stat().st_size / (1024 * 1024)
        checksum = compute_sha256(installer_exe)

        checksum_file = output_dir / "Dot-Setup-x64.exe.sha256"
        with open(checksum_file, "w", encoding="utf-8") as f:
            f.write(f"{checksum}  Dot-Setup-x64.exe\n")

        log("Compilation successful.")
        log(f"Installer: {installer_exe}")
        log(f"File Size: {size_mb:.2f} MB")
        log(f"SHA256: {checksum}")
        return 0

    except Exception as err:
        log_error(f"Failed to compile installer: {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

