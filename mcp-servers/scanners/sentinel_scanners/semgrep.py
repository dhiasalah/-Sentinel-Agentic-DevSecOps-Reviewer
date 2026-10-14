import sys
from pathlib import Path

from sentinel_scanners.models import Finding
from sentinel_scanners.runner import Job, Mount, read_result, run_job, scratch_dir

SEMGREP_IMAGE = "semgrep/semgrep@sha256:93963d9295a366f59e4850127b1550400ee7b388f04fe144e4a1f6325d96e01b"


def run_semgrep(target: Path) -> dict:
    target = target.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"scan target is not a directory: {target}")
    with scratch_dir("sentinel-semgrep-") as out:
        run_job(Job(
            name="semgrep",
            image=SEMGREP_IMAGE,
            # Needs the network once: the p/python rules come from the Semgrep registry.
            network=True,
            read_only=False,
            env={"HOME": "/tmp"},
            mounts=[Mount("/src", path=target), Mount("/out", path=out, read_only=False)],
            args=["semgrep", "scan", "--config", "p/python", "--json", "--quiet", "--metrics=off",
                  "--output", "/out/result.json", "/src"],
            timeout=300,
        ))
        return read_result(out / "result.json") or {"results": []}


def parse_findings(raw: dict) -> list[Finding]:
    findings = []
    for result in raw.get("results", []):
        extra = result.get("extra", {})
        cwe = extra.get("metadata", {}).get("cwe", [])
        if isinstance(cwe, str):
            cwe = [cwe]
        findings.append(
            Finding(
                tool="semgrep",
                rule_id=result["check_id"],
                severity=extra.get("severity", "INFO"),
                message=extra.get("message", "").strip(),
                file=result["path"].removeprefix("/src/"),
                line=result["start"]["line"],
                cwe=cwe,
            )
        )
    return findings

if __name__ == "__main__":
    target = Path(sys.argv[1])
    findings = parse_findings(run_semgrep(target))
    for f in findings:
        print(f"[{f.severity:7}] {f.file}:{f.line}  {f.rule_id}")
    print(f"\n{len(findings)} findings")
