import json

import pytest

from sentinel_scanners import trivy
from sentinel_scanners.trivy import parse_findings, run_trivy


def vuln(cve, severity, fixed="2.0", cwes=None):
    return {"VulnerabilityID": cve, "PkgName": "flask", "InstalledVersion": "0.12.2", "FixedVersion": fixed,
            "Severity": severity, "CweIDs": cwes, "PkgIdentifier": {"UID": "u1"}}


SAMPLE = {"Results": [{
    "Target": "requirements.txt",
    "Packages": [{"Name": "flask", "Identifier": {"UID": "u1"}, "Locations": [{"StartLine": 3, "EndLine": 3}]}],
    "Vulnerabilities": [vuln("CVE-2", "LOW", "3.1", ["CWE-524"]), vuln("CVE-1", "HIGH", "1.0", ["CWE-20"])],
}]}


@pytest.fixture
def captured(monkeypatch):
    jobs = []
    monkeypatch.setattr(trivy, "run_job", jobs.append)
    return jobs


def test_one_finding_per_package_on_its_line_with_the_worst_severity():
    [finding] = parse_findings(SAMPLE)
    assert (finding.tool, finding.file, finding.line) == ("trivy", "requirements.txt", 3)
    assert finding.severity == "HIGH"
    assert finding.cwe == ["CWE-1395", "CWE-20", "CWE-524"]
    assert "CVE-1, CVE-2" in finding.message and "1.0, 3.1" in finding.message


def test_clean_repo_has_no_findings():
    assert parse_findings({"Results": [{"Target": "requirements.txt", "Packages": []}]}) == []
    assert parse_findings({}) == []


def test_db_download_never_sees_the_code_and_the_scan_is_offline(tmp_path, captured):
    run_trivy(tmp_path)
    download, scan = captured
    assert download.network is True and download.user is None
    assert not any(m.path for m in download.mounts) and "--download-db-only" in download.args
    assert scan.network is False and scan.read_only is True
    assert any(m.cache == trivy.CACHE_VOLUME and m.read_only for m in scan.mounts)
    for flag in ("--skip-db-update", "--offline-scan", "--scanners", "vuln"):
        assert flag in scan.args
