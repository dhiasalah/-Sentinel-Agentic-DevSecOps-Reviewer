import os
from pathlib import Path

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from sentinel_scanners import checkov, gitleaks, semgrep, trivy
from sentinel_scanners.models import Finding

server = MCPServer(
    "sentinel-scanners",
    instructions="Security scanners for one repository, chosen when the server starts. Each tool scans all of it.",
)
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def scan_root() -> Path:
    root = os.environ.get("SENTINEL_SCAN_ROOT")
    if not root:
        raise RuntimeError("SENTINEL_SCAN_ROOT is not set")
    return Path(root)


@server.tool(name="semgrep", annotations=READ_ONLY)
def scan_semgrep() -> list[Finding]:
    """Find insecure code patterns in the repository's Python files (SAST)."""
    return semgrep.parse_findings(semgrep.run_semgrep(scan_root()))


@server.tool(name="gitleaks", annotations=READ_ONLY)
def scan_gitleaks() -> list[Finding]:
    """Find hardcoded secrets in any file of the repository. Secret values are never returned."""
    return gitleaks.parse_findings(gitleaks.run_gitleaks(scan_root()))


@server.tool(name="trivy", annotations=READ_ONLY)
def scan_trivy() -> list[Finding]:
    """Find dependencies with known vulnerabilities (CVEs), one finding per vulnerable package (SCA)."""
    return trivy.parse_findings(trivy.run_trivy(scan_root()))


@server.tool(name="checkov", annotations=READ_ONLY)
def scan_checkov() -> list[Finding]:
    """Find insecure Dockerfile, Terraform, Kubernetes and GitHub Actions configuration (IaC)."""
    return checkov.parse_findings(checkov.run_checkov(scan_root()))


if __name__ == "__main__":
    server.run("stdio")
