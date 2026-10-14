from pathlib import Path

from sentinel_scanners.models import Finding
from sentinel_scanners.runner import Job, Mount, read_result, run_job, scratch_dir

TRIVY_IMAGE = "aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
CACHE_VOLUME = "sentinel-trivy-cache"
SEVERITY_ORDER = ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
MAX_IDS = 10


def update_db() -> None:
    """Phase 1: download the vulnerability database. The only Trivy run with network and no code.
    It runs as the image's own user (root) because it writes the shared cache."""
    run_job(Job(
        name="trivy-db",
        image=TRIVY_IMAGE,
        network=True,
        read_only=False,
        user=None,
        timeout=600,
        mounts=[Mount("/cache", cache=CACHE_VOLUME, read_only=False)],
        args=["fs", "--cache-dir", "/cache", "--download-db-only", "--no-progress", "--quiet"],
    ))


def run_trivy(target: Path) -> dict:
    target = target.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"scan target is not a directory: {target}")
    update_db()
    # Phase 2: scan with no network, the database read-only.
    with scratch_dir("sentinel-trivy-") as out:
        run_job(Job(
            name="trivy",
            image=TRIVY_IMAGE,
            mounts=[
                Mount("/src", path=target),
                Mount("/cache", cache=CACHE_VOLUME),
                Mount("/out", path=out, read_only=False),
            ],
            args=["fs", "--cache-dir", "/cache", "--skip-db-update", "--offline-scan",
                  "--scanners", "vuln", "--list-all-pkgs", "--format", "json", "--quiet",
                  "--output", "/out/result.json", "/src"],
        ))
        return read_result(out / "result.json") or {}


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
