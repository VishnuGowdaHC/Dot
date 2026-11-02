"""
Build the full redistributable directory layout for Dot.
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
    print(f"[DIST BUILDER] {message}")


def log_error(message: str) -> None:
    """Print an error message."""
    print(f"[DIST BUILDER ERROR] {message}", file=sys.stderr)


def clean_directory(target_dir: Path) -> None:
    """Remove target directory if it exists and recreate it."""
    if target_dir.exists():
        log(f"Cleaning previous build at {target_dir}...")
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)


def build_frontend(root_dir: Path, dist_frontend_dir: Path) -> None:
    """Prepare frontend assets and Neutralino binaries."""
    src_frontend = root_dir / "frontend"
    log("Preparing frontend assets...")

    # Build fresh Neutralino resources if npm is available
    npm_cmd = shutil.which("npm")
    if npm_cmd:
        try:
            log("Compiling frontend assets and Neutralino bundle (npm run build)...")
            subprocess.run(["cmd", "/c", "npm", "run", "build"], cwd=str(src_frontend), check=True)
        except Exception as e:
            log(f"Frontend build warning: {e}")

    dist_frontend_dir.mkdir(parents=True, exist_ok=True)

    # Candidate source binaries for Neutralino
    neu_candidates = [
        src_frontend / "out" / "Dot" / "Dot-win_x64.exe",
        src_frontend / "bin" / "Dot-win_x64.exe",
        src_frontend / "bin" / "neutralino-win_x64.exe",
    ]

    binary_found = False
    for cand in neu_candidates:
        if cand.exists():
            dst_exe = dist_frontend_dir / "Dot-win_x64.exe"
            shutil.copy2(cand, dst_exe)
            log(f"Copied frontend binary: {cand.name} -> {dst_exe.name}")
            binary_found = True
            break

    if not binary_found:
        log_error("Frontend binary not found in frontend/bin.")
        raise FileNotFoundError("Missing Neutralino desktop binary.")

    # Copy resources.neu
    neu_res_candidates = [
        src_frontend / "out" / "Dot" / "resources.neu",
        src_frontend / "bin" / "resources.neu",
        src_frontend / "resources.neu",
    ]
    res_found = False
    for res in neu_res_candidates:
        if res.exists():
            dst_res = dist_frontend_dir / "resources.neu"
            shutil.copy2(res, dst_res)
            log(f"Copied frontend resources: {res.name}")
            res_found = True
            break

    if not res_found:
        log_error("resources.neu not found.")
        raise FileNotFoundError("Missing resources.neu.")

    # Copy dist folder for static assets
    src_dist = src_frontend / "dist"
    dst_dist = dist_frontend_dir / "dist"
    if src_dist.exists():
        shutil.copytree(
            src_dist,
            dst_dist,
            ignore=shutil.ignore_patterns("*.png", "*.jpg", "*.svg", "__pycache__"),
        )
        # Copy essential web assets
        for asset in ["index.html", "output.css", "favicon.ico", "neutralino.js"]:
            asset_path = src_dist / asset
            if asset_path.exists():
                shutil.copy2(asset_path, dst_dist / asset)
        log("Copied static web assets.")


def copy_backend(root_dir: Path, dist_dir: Path) -> None:
    """Copy backend server code and package definitions."""
    src_backend = root_dir / "backend"
    dst_backend = dist_dir / "backend"

    log("Copying backend application code...")
    shutil.copytree(
        src_backend,
        dst_backend,
        ignore=shutil.ignore_patterns(
            ".venv",
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".pytest_cache",
            "tests",
            "*.log",
        ),
    )


def copy_launcher_and_configs(root_dir: Path, dist_dir: Path) -> None:
    """Copy launcher, setup wizard, icons, and configuration templates."""
    files_to_copy = [
        "Dot.exe",
        "launcher.pyw",
        "setup.py",
        "app_icon.ico",
        "requirements.txt",
        "appConfig.json",
    ]

    for fname in files_to_copy:
        src = root_dir / fname
        if src.exists():
            shutil.copy2(src, dist_dir / fname)
            log(f"Copied root file: {fname}")

    # Ensure required empty runtime directories exist
    (dist_dir / "bin").mkdir(exist_ok=True)
    (dist_dir / "logs").mkdir(exist_ok=True)


def create_readme(dist_dir: Path) -> None:
    """Create a concise README text file for users."""
    readme_path = dist_dir / "README.txt"
    content = (
        "Dot Assistant\n"
        "=============\n\n"
        "Start Dot by launching Dot.exe.\n\n"
        "First Launch:\n"
        "The setup wizard will open automatically.\n"
        "Configure Cloud API keys or download a local model.\n\n"
        "Requirements:\n"
        "Windows 10 or Windows 11 (64-bit).\n"
        "No Python installation is required.\n"
    )
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)
    log("Created README.txt.")


def main() -> int:
    """Execute the full distribution assembly."""
    parser = argparse.ArgumentParser(description="Build complete Dot distribution package.")
    parser.add_argument(
        "--venv",
        type=Path,
        default=Path(".venv"),
        help="Path to source virtual environment",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist") / "Dot",
        help="Path to output distribution folder",
    )
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="Skip bundling the Python runtime",
    )
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    dist_dir = args.output

    log(f"Starting distribution build in {dist_dir}...")

    try:
        dist_dir.mkdir(parents=True, exist_ok=True)

        # 1. Build and copy frontend
        build_frontend(root_dir, dist_dir / "frontend")

        # 2. Copy backend
        copy_backend(root_dir, dist_dir)

        # 3. Copy launcher and configs
        copy_launcher_and_configs(root_dir, dist_dir)

        # 4. Create README
        create_readme(dist_dir)

        # 5. Bundle runtime
        if not args.skip_runtime:
            log("Running runtime bundling script...")
            bundler_script = root_dir / "scripts" / "bundle_runtime.py"
            cmd = [
                sys.executable,
                str(bundler_script),
                "--venv",
                str(args.venv),
                "--output",
                str(dist_dir / "runtime"),
            ]
            result = subprocess.run(cmd, cwd=str(root_dir))
            if result.returncode != 0:
                log_error("Runtime bundling failed.")
                return 1

        log("Distribution build finished successfully.")
        return 0

    except Exception as err:
        log_error(f"Distribution build failed: {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
