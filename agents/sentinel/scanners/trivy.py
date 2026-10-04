import json
import subprocess
from pathlib import Path

from sentinel.models import Finding

TRIVY_IMAGE = "aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
CACHE_VOLUME = "sentinel-trivy-cache"
SEVERITY_ORDER = ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
MAX_IDS = 10


def _docker(cmd: list[str], timeout: int) -> str:
    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"trivy failed (exit {proc.returncode}): {proc.stderr[-500:]}")
    return proc.stdout


def update_db() -> None:
    _docker([
        "docker", "run", "--rm",
        "-v", f"{CACHE_VOLUME}:/cache",
        TRIVY_IMAGE,
        "fs", "--cache-dir", "/cache", "--download-db-only", "--no-progress", "--quiet",
    ], timeout=600)


def run_trivy(target: Path) -> dict:
    target = target.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"scan target is not a directory: {target}")
    update_db()
    return json.loads(_docker([
        "docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp",
        "-v", f"{target}:/src:ro",
        "-v", f"{CACHE_VOLUME}:/cache:ro",
        TRIVY_IMAGE,
        "fs", "--cache-dir", "/cache", "--skip-db-update", "--offline-scan",
        "--scanners", "vuln", "--list-all-pkgs",
        "--format", "json", "--quiet",
        "/src",
    ], timeout=300))

def parse_findings(raw: dict) -> list[Finding]:
    findings = []
    for result in raw.get("Results") or []:
        lines = {
            pkg["Identifier"]["UID"]: (pkg.get("Locations") or [{}])[0].get("StartLine", 1)
            for pkg in result.get("Packages") or []
        }
        by_package: dict[str, list[dict]] = {}
        for vuln in result.get("Vulnerabilities") or []:
            by_package.setdefault(vuln["PkgIdentifier"]["UID"], []).append(vuln)
        for uid, vulns in by_package.items():
            pkg = vulns[0]
            ids = sorted(v["VulnerabilityID"] for v in vulns)
            fixed = sorted({v["FixedVersion"] for v in vulns if v.get("FixedVersion")})
            shown = ", ".join(ids[:MAX_IDS]) + (" ..." if len(ids) > MAX_IDS else "")
            findings.append(Finding(
                tool="trivy",
                rule_id=f"vulnerable-dependency:{pkg['PkgName']}",
                severity=max((v["Severity"] for v in vulns), key=SEVERITY_ORDER.index),
                message=(f"{pkg['PkgName']} {pkg['InstalledVersion']} has {len(ids)} known vulnerabilities "
                         f"({shown}). Fixed in: {', '.join(fixed) or 'no fixed version yet'}"),
                file=result["Target"],
                line=lines.get(uid, 1),
                cwe=["CWE-1395", *sorted({c for v in vulns for c in v.get("CweIDs") or []})],
            ))
    return findings
