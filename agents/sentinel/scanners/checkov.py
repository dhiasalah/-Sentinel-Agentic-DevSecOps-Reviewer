import json
import subprocess
from pathlib import Path

from sentinel.models import Finding

CHECKOV_IMAGE = "bridgecrew/checkov:3.3.16@sha256:7407699a91a556849ae66e05c3753f58cf0ce922aa6ddfac7839aad4f390c016"
CONFIG_DIR = Path(__file__).parent / "config"
REPO_CONFIGS = (".checkov.yaml", ".checkov.yml")
FRAMEWORKS = ["dockerfile", "terraform", "kubernetes", "cloudformation", "github_actions"]
RULES = {
    "CKV_DOCKER_3": ("WARNING", ["CWE-250"]),
    "CKV_DOCKER_8": ("WARNING", ["CWE-250"]),
    "CKV_DOCKER_7": ("INFO", ["CWE-1357"]),
}
SUPPRESSED = " (the repo turned this check off with a checkov:skip comment; Sentinel reports it anyway)"


def run_checkov(target: Path) -> list[dict]:
    target = target.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"scan target is not a directory: {target}")
    mounts = ["-v", f"{target}:/src:ro"]
    for name in REPO_CONFIGS:
        repo_config = target / name
        if repo_config.is_symlink() or (repo_config.exists() and not repo_config.is_file()):
            raise RuntimeError(f"refusing to scan: {name} is not a regular file")
        if repo_config.exists():
            mounts += ["-v", f"{CONFIG_DIR / 'checkov.yaml'}:/src/{name}:ro"]
    cmd = [
        "docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp",
        "-e", "BC_SKIP_MAPPING=TRUE",
        *mounts,
        CHECKOV_IMAGE,
        "-d", "/src",
        "--framework", *FRAMEWORKS,
        "--skip-download", "--soft-fail", "--compact",
        "-o", "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"checkov failed (exit {proc.returncode}): {proc.stderr[-500:]}")
    raw = json.loads(proc.stdout)
    return raw if isinstance(raw, list) else [raw]

def parse_findings(reports: list[dict]) -> list[Finding]:
    findings = []
    for report in reports:
        results = report.get("results", {})
        for key, note in (("failed_checks", ""), ("skipped_checks", SUPPRESSED)):
            for check in results.get(key, []):
                severity, cwe = RULES.get(check["check_id"], ("INFO", []))
                first, last = check["file_line_range"]
                findings.append(Finding(
                    tool="checkov",
                    rule_id=check["check_id"],
                    severity=severity,
                    message=check["check_name"] + note,
                    file=check["file_path"].lstrip("/"),
                    line=max(first, 1),
                    end_line=max(last, 1),
                    cwe=cwe,
                ))
    return findings
