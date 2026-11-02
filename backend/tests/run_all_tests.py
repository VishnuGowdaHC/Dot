"""
Test runner script executing all Dot tool suites.
Runs unit and integration tests and prints a formatted summary table.
"""

import sys
import os
import time
import unittest
from pathlib import Path

# Add backend directory to module search path.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ANSI terminal color codes.
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

TEST_MODULES = [
    "tests.test_browser_tools",
    "tests.test_desktop_tools",
    "tests.test_native_tools",
    "tests.test_app_opener",
    "tests.test_voice_subsystem",
    "tests.test_logging",
    "tests.test_memory_compactor",
]


def run_suite(module_name: str) -> dict:
    """Loads and runs a single test module."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(module_name)
    start_time = time.time()
    with open(os.devnull, "w") as devnull:
        runner = unittest.TextTestRunner(verbosity=0, stream=devnull)
        result = runner.run(suite)
    duration = time.time() - start_time

    return {
        "module": module_name.split(".")[-1],
        "total": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "duration": duration,
        "success": result.wasSuccessful(),
    }


def main():
    """Executes all test modules and prints a summary report."""
    print(f"\n{BOLD}{CYAN}=== Running Dot Tool Test Suites ==={RESET}\n")

    results = []
    total_passed = 0
    total_failed = 0
    total_time = 0.0

    for mod in TEST_MODULES:
        sys.stdout.write(f"Running {mod}... ")
        sys.stdout.flush()
        res = run_suite(mod)
        results.append(res)
        total_time += res["duration"]

        if res["success"]:
            total_passed += res["total"]
            print(f"{GREEN}PASS{RESET} ({res['total']} tests, {res['duration']:.2f}s)")
        else:
            total_failed += (res["failures"] + res["errors"])
            print(f"{RED}FAIL{RESET} ({res['failures']} fails, {res['errors']} errors in {res['duration']:.2f}s)")

    # Print summary table
    print("\n" + "=" * 70)
    print(f"{BOLD}{'TEST SUITE':<30} {'TESTS':<10} {'STATUS':<10} {'TIME':<10}{RESET}")
    print("-" * 70)

    for r in results:
        status_color = GREEN if r["success"] else RED
        status_text = "PASSED" if r["success"] else "FAILED"
        print(f"{r['module']:<30} {r['total']:<10} {status_color}{status_text:<10}{RESET} {r['duration']:>6.2f}s")

    print("-" * 70)
    summary_color = GREEN if total_failed == 0 else RED
    print(
        f"{BOLD}TOTAL:{RESET} {total_passed + total_failed} tests | "
        f"{GREEN}{total_passed} passed{RESET} | "
        f"{RED}{total_failed} failed{RESET} | "
        f"Total duration: {total_time:.2f}s"
    )
    print("=" * 70 + "\n")

    if total_failed > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
