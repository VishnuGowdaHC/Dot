"""
Bundle and prune an isolated portable Python runtime for Dot distribution.
This script follows ASD-STE100 standards.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def log(message: str) -> None:
    """Print an informational log message."""
    print(f"[RUNTIME BUNDLER] {message}")


def log_error(message: str) -> None:
    """Print an error message."""
    print(f"[RUNTIME BUNDLER ERROR] {message}", file=sys.stderr)


def get_base_python_dir(venv_dir: Path) -> Path:
    """Find the base Python installation directory from pyvenv.cfg or sys.base_prefix."""
    cfg_path = venv_dir / "pyvenv.cfg"
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("home ="):
                    home_dir = Path(line.split("=", 1)[1].strip())
                    if home_dir.exists():
                        return home_dir

    base_prefix = Path(sys.base_prefix)
    if base_prefix.exists():
        return base_prefix

    raise RuntimeError("Cannot locate base Python directory.")


def copy_python_binaries(base_dir: Path, target_dir: Path) -> None:
    """Copy Python binaries, DLLs, and standard libraries to the target runtime."""
    log(f"Copying Python base from {base_dir} to {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    # Core executables and shared libraries
    bin_files = [
        "python.exe",
        "pythonw.exe",
        "python3.dll",
        "python312.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
    ]

    for fname in bin_files:
        src = base_dir / fname
        if src.exists():
            shutil.copy2(src, target_dir / fname)
            log(f"Copied binary: {fname}")

    # Copy DLLs folder
    dlls_src = base_dir / "DLLs"
    dlls_dst = target_dir / "DLLs"
    if dlls_src.exists() and not dlls_dst.exists():
        log("Copying DLLs folder...")
        shutil.copytree(dlls_src, dlls_dst)

    # Copy standard library Lib folder (excluding site-packages)
    lib_src = base_dir / "Lib"
    lib_dst = target_dir / "Lib"
    if lib_src.exists() and not lib_dst.exists():
        log("Copying standard library Lib folder...")
        shutil.copytree(
            lib_src,
            lib_dst,
            ignore=shutil.ignore_patterns(
                "site-packages",
                "test",
                "tests",
                "idlelib",
                "ensurepip",
                "__pycache__",
            ),
        )

    # Copy tcl folder for Tkinter and CustomTkinter support
    tcl_src = base_dir / "tcl"
    tcl_dst = target_dir / "tcl"
    if tcl_src.exists() and not tcl_dst.exists():
        log("Copying tcl directory for Tkinter support...")
        shutil.copytree(tcl_src, tcl_dst)


def copy_site_packages(venv_dir: Path, target_dir: Path) -> None:
    """Copy installed packages from the virtual environment to target runtime."""
    src_sp = venv_dir / "Lib" / "site-packages"
    dst_sp = target_dir / "Lib" / "site-packages"

    if not src_sp.exists():
        raise RuntimeError(f"Source site-packages not found: {src_sp}")

    dst_sp.mkdir(parents=True, exist_ok=True)
    log(f"Copying packages from {src_sp} to {dst_sp}...")

    # Copy packages while ignoring cache files
    for item in src_sp.iterdir():
        target_item = dst_sp / item.name
        if target_item.exists():
            continue

        if item.is_dir():
            if item.name == "__pycache__":
                continue
            shutil.copytree(
                item,
                target_item,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
        else:
            if not item.name.endswith((".pyc", ".pyo")):
                shutil.copy2(item, target_item)


def prune_runtime(target_dir: Path) -> None:
    """Remove cache and unnecessary debug files to reduce package size."""
    log("Pruning runtime to reduce size...")
    removed_bytes = 0
    removed_count = 0

    # Only purge bytecode caches. Do not purge test directories because packages like torch require them.
    purge_dirs = {"__pycache__"}

    # Patterns for file extensions to remove
    purge_exts = {".pyc", ".pyo", ".pdb"}

    for root, dirs, files in os.walk(target_dir, topdown=False):
        current_path = Path(root)

        # Remove matching directories
        for d in list(dirs):
            if d in purge_dirs:
                dir_path = current_path / d
                try:
                    for p in dir_path.rglob("*"):
                        if p.is_file():
                            removed_bytes += p.stat().st_size
                            removed_count += 1
                    shutil.rmtree(dir_path, ignore_errors=True)
                    dirs.remove(d)
                except Exception:
                    pass

        # Remove matching files
        for f in files:
            file_path = current_path / f
            if file_path.suffix.lower() in purge_exts:
                try:
                    removed_bytes += file_path.stat().st_size
                    removed_count += 1
                    file_path.unlink()
                except Exception:
                    pass

    mb_saved = removed_bytes / (1024 * 1024)
    log(f"Pruning complete. Removed {removed_count} files ({mb_saved:.1f} MB saved).")


def verify_runtime(target_dir: Path) -> bool:
    """Verify the bundled runtime by importing key modules."""
    py_exe = target_dir / "python.exe"
    if not py_exe.exists():
        log_error(f"Python executable missing: {py_exe}")
        return False

    test_cmd = (
        "import sys, os;"
        "import fastapi, uvicorn, pydantic;"
        "import torch, chromadb;"
        "import customtkinter;"
        "print('PORTABLE_RUNTIME_VERIFIED')"
    )

    log("Verifying bundled runtime imports...")
    result = subprocess.run(
        [str(py_exe), "-c", test_cmd],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        log_error("Verification failed:")
        log_error(result.stderr)
        return False

    if "PORTABLE_RUNTIME_VERIFIED" in result.stdout:
        log("Verification successful. All core modules import correctly.")
        return True

    log_error("Unexpected verification output:")
    log_error(result.stdout)
    return False


def main() -> int:
    """Run the runtime bundling pipeline."""
    parser = argparse.ArgumentParser(description="Bundle portable Python runtime for Dot.")
    parser.add_argument(
        "--venv",
        type=Path,
        default=Path(".venv"),
        help="Path to the source virtual environment (default: .venv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist") / "Dot" / "runtime",
        help="Path to the destination runtime directory",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove destination runtime directory before building",
    )
    parser.add_argument(
        "--skip-prune",
        action="store_true",
        help="Skip pruning cache and test files",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only run verification on existing output directory",
    )

    args = parser.parse_args()

    if args.verify_only:
        success = verify_runtime(args.output)
        return 0 if success else 1

    try:
        if args.clean and args.output.exists():
            log(f"Cleaning destination directory {args.output}...")
            shutil.rmtree(args.output, ignore_errors=True)

        base_dir = get_base_python_dir(args.venv)
        copy_python_binaries(base_dir, args.output)
        copy_site_packages(args.venv, args.output)

        if not args.skip_prune:
            prune_runtime(args.output)

        success = verify_runtime(args.output)
        if not success:
            log_error("Runtime verification failed.")
            return 1

        log("Runtime bundle created successfully.")
        return 0
    except Exception as err:
        log_error(f"Bundle generation failed: {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

