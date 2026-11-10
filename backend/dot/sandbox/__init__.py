"""
Sandbox subsystem for Dot.
Provides lightweight container lifecycle management, command execution, and human intervention controls.
Complies with ASD-STE100 technical writing standards.
"""

from dot.sandbox.manager import (
    is_docker_available,
    is_sandbox_running,
    start_sandbox,
    stop_sandbox,
    pause_sandbox,
    unpause_sandbox,
    ensure_sandbox_ready,
)
from dot.sandbox.executor import exec_in_sandbox
from dot.sandbox.intervention import InterventionManager, get_intervention_manager

__all__ = [
    "is_docker_available",
    "is_sandbox_running",
    "start_sandbox",
    "stop_sandbox",
    "pause_sandbox",
    "unpause_sandbox",
    "ensure_sandbox_ready",
    "exec_in_sandbox",
    "InterventionManager",
    "get_intervention_manager",
]

