import json
import subprocess
import sys
from pathlib import Path

from sentinel.models import Finding

SEMGREP_IMAGE = "semgrep/semgrep"


def run_semgrep(target: Path) -> dict:
    target = target.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"scan target is not a directory: {target}")
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{target}:/src:ro",
        SEMGREP_IMAGE,
        "semgrep", "scan",
        "--config", "p/python",
        "--json", "--quiet", "--metrics=off",
        "/src",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"semgrep failed (exit {proc.returncode}): {proc.stderr[-500:]}")
    return json.loads(proc.stdout)


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
