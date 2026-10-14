from pathlib import Path

from sentinel_scanners.models import Finding
from sentinel_scanners.runner import Job, Mount, read_result, run_job, scratch_dir
from sentinel_scanners.staging import stage_config

CHECKOV_IMAGE = "bridgecrew/checkov:3.3.16@sha256:7407699a91a556849ae66e05c3753f58cf0ce922aa6ddfac7839aad4f390c016"
CHECKOV_RESULT = "results_json.json"  # the file Checkov writes into --output-file-path
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
    for name in REPO_CONFIGS:
        repo_config = target / name
        if repo_config.is_symlink() or (repo_config.exists() and not repo_config.is_file()):
            raise RuntimeError(f"refusing to scan: {name} is not a regular file")
    with scratch_dir("sentinel-checkov-") as out:
        config = stage_config(out)
        mounts = [Mount("/src", path=target), Mount("/out", path=out, read_only=False)]
        for name in REPO_CONFIGS:
            if (target / name).exists():
                # The repo's own config could switch checks off: replace it with ours.
                mounts.append(Mount(f"/src/{name}", path=config / "checkov.yaml"))
        run_job(Job(
            name="checkov",
            image=CHECKOV_IMAGE,
            mounts=mounts,
            env={"BC_SKIP_MAPPING": "TRUE"},
            args=["-d", "/src", "--framework", *FRAMEWORKS, "--skip-download", "--soft-fail",
                  "--compact", "-o", "json", "--output-file-path", "/out"],
        ))
        reports = read_result(out / CHECKOV_RESULT) or []
    return reports if isinstance(reports, list) else [reports]


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
