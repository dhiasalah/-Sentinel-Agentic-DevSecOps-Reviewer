import json
import subprocess
from pathlib import Path

from sentinel_scanners.models import Finding

GITLEAKS_IMAGE = "zricethezav/gitleaks:v8.24.0@sha256:2bcceac45179b3a91bff11a824d0fb952585b429e54fc928728b1d4d5c3e5176"
CONFIG_DIR = Path(__file__).parent / "config"


def run_gitleaks(target: Path) -> list[dict]:
    target = target.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"scan target is not a directory: {target}")
    mounts = ["-v", f"{target}:/src:ro", "-v", f"{CONFIG_DIR}:/config:ro"]
    repo_ignore = target / ".gitleaksignore"
    if repo_ignore.is_symlink() or (repo_ignore.exists() and not repo_ignore.is_file()):
        raise RuntimeError("refusing to scan: .gitleaksignore is not a regular file")
    if repo_ignore.exists():
        mounts += ["-v", f"{CONFIG_DIR / 'empty'}:/src/.gitleaksignore:ro"]
    cmd = [
        "docker", "run", "--rm", "--network", "none",
        *mounts,
        GITLEAKS_IMAGE,
        "dir", "/src",
        "--config", "/config/gitleaks.toml",
        "--ignore-gitleaks-allow",
        "--redact",
        "--no-banner", "--log-level", "error",
        "--report-format", "json", "--report-path", "-",
        "--exit-code", "0",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"gitleaks failed (exit {proc.returncode}): {proc.stderr[-500:]}")
    return json.loads(proc.stdout)

def parse_findings(raw: list[dict]) -> list[Finding]:
    return [
        Finding(
            tool="gitleaks",
            rule_id=leak["RuleID"],
            severity="ERROR",
            message=f"{leak['Description']} (value not shown)",
            file=leak["File"].removeprefix("/src/"),
            line=leak["StartLine"],
            end_line=leak["EndLine"],
            cwe=["CWE-798"],
        )
        for leak in raw
    ]
