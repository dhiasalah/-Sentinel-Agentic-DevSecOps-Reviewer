"""Lets the worker use the scanner runner (mcp-servers/scanners) in-process, e.g. for the fix sandbox.

Same layout trick as mcp_scanners.py: the scanners folder sits next to agents/ in the repo and at /app in the
worker image, so it is found from this file's location."""

import sys
from pathlib import Path

SCANNERS_DIR = Path(__file__).resolve().parents[2] / "mcp-servers" / "scanners"
if str(SCANNERS_DIR) not in sys.path:
    sys.path.append(str(SCANNERS_DIR))

from sentinel_scanners.runner import (  # noqa: E402  (must come after the path change)
    RUNNER_ENV_KEYS,
    Job,
    Mount,
    ScanJobError,
    run_job,
    workspace_root,
)

__all__ = ["RUNNER_ENV_KEYS", "Job", "Mount", "ScanJobError", "run_job", "workspace_root"]
