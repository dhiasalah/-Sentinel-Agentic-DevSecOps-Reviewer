from pathlib import Path

from sentinel_scanners.models import Finding
from sentinel_scanners.runner import Job, Mount, read_result, run_job, scratch_dir
from sentinel_scanners.staging import stage_config

GITLEAKS_IMAGE = "zricethezav/gitleaks:v8.24.0@sha256:2bcceac45179b3a91bff11a824d0fb952585b429e54fc928728b1d4d5c3e5176"


def run_gitleaks(target: Path) -> list[dict]:
    target = target.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"scan target is not a directory: {target}")
    repo_ignore = target / ".gitleaksignore"
    if repo_ignore.is_symlink() or (repo_ignore.exists() and not repo_ignore.is_file()):
        raise RuntimeError("refusing to scan: .gitleaksignore is not a regular file")
    with scratch_dir("sentinel-gitleaks-") as out:
        config = stage_config(out)
        mounts = [Mount("/src", path=target), Mount("/config", path=config),
                  Mount("/out", path=out, read_only=False)]
        if repo_ignore.exists():
            # The repo's own .gitleaksignore could hide a secret: replace it with an empty file.
            mounts.append(Mount("/src/.gitleaksignore", path=config / "empty"))
        run_job(Job(
            name="gitleaks",
            image=GITLEAKS_IMAGE,
            mounts=mounts,
            args=["dir", "/src", "--config", "/config/gitleaks.toml", "--ignore-gitleaks-allow",
                  "--redact", "--no-banner", "--log-level", "error",
                  "--report-format", "json", "--report-path", "/out/result.json", "--exit-code", "0"],
        ))
        return read_result(out / "result.json") or []

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
        for leak in raw or []
    ]
