from pathlib import Path

import httpx
import pytest

from sentinel_scanners import runner
from sentinel_scanners.runner import (
    Job, KubernetesRunner, Mount, ScanJobError, ServiceAccountAuth, docker_command, job_manifest, k8s_memory,
    read_result, scratch_dir,
)


def job(**changes):
    base = dict(name="demo", image="example/scanner@sha256:abc", args=["scan", "/src"],
                mounts=[Mount("/src", path=Path("/work/repo"))])
    return Job(**(base | changes))


def test_docker_scanner_gets_every_hardening_flag_by_default(tmp_path):
    cmd = docker_command(job(mounts=[Mount("/src", path=tmp_path)]))
    for flag in ("--cap-drop ALL", "--security-opt no-new-privileges", "--network none", "--read-only",
                 "--user 65534:65534", "--memory 1g", "--pids-limit 256"):
        assert flag in " ".join(cmd)
    assert cmd[-3:] == ["example/scanner@sha256:abc", "scan", "/src"]


def test_network_and_writable_root_are_opt_in(tmp_path):
    cmd = " ".join(docker_command(job(network=True, read_only=False, user=None, mounts=[Mount("/src", path=tmp_path)])))
    assert "--network none" not in cmd and "--read-only" not in cmd and "--user" not in cmd


def test_mount_needs_exactly_one_source():
    with pytest.raises(ValueError):
        Mount("/src")
    with pytest.raises(ValueError):
        Mount("/src", path=Path("/x"), cache="y")


def test_read_only_and_cache_mounts_render_as_docker_volumes(tmp_path):
    cmd = docker_command(job(mounts=[Mount("/cache", cache="sentinel-trivy-cache"),
                                     Mount("/out", path=tmp_path, read_only=False)]))
    assert "sentinel-trivy-cache:/cache:ro" in cmd
    assert f"{tmp_path.resolve()}:/out" in cmd


def test_kubernetes_manifest_is_locked_down_and_uses_a_sub_path(tmp_path):
    workspace = tmp_path
    scan = workspace / "sentinel-semgrep-x" / "repo"
    manifest = job_manifest(job(mounts=[Mount("/src", path=scan), Mount("/cache", cache="sentinel-trivy-cache")]),
                            namespace="sentinel-scans", workspace=workspace, claim="sentinel-workspace",
                            name="demo-abc")
    spec = manifest["spec"]
    pod = spec["template"]["spec"]
    container = pod["containers"][0]
    assert manifest["kind"] == "Job" and manifest["metadata"]["namespace"] == "sentinel-scans"
    assert spec["backoffLimit"] == 0 and spec["activeDeadlineSeconds"] == 300
    assert pod["automountServiceAccountToken"] is False and pod["restartPolicy"] == "Never"
    assert pod["securityContext"]["runAsNonRoot"] is True and pod["securityContext"]["runAsUser"] == 65534
    assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"] == {"drop": ["ALL"]}
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["resources"]["limits"] == {"memory": "1Gi", "cpu": "1"}
    volumes = {v["name"]: v for v in pod["volumes"]}
    assert volumes["mount-0"]["persistentVolumeClaim"]["claimName"] == "sentinel-workspace"
    assert {"name": "mount-0", "mountPath": "/src", "subPath": "sentinel-semgrep-x/repo", "readOnly": True} \
        in container["volumeMounts"]
    assert volumes["mount-1"]["persistentVolumeClaim"]["claimName"] == "sentinel-trivy-cache"
    assert "tmp" in volumes  # /tmp in memory because the root filesystem is read-only
    assert manifest["metadata"]["labels"]["sentinel.dev/network"] == "false"


def test_a_job_that_needs_the_network_is_labelled_for_its_policy(tmp_path):
    manifest = job_manifest(job(network=True, read_only=False, user=None, mounts=[Mount("/src", path=tmp_path / "r")]),
                            namespace="n", workspace=tmp_path, claim="c", name="x")
    assert manifest["metadata"]["labels"]["sentinel.dev/network"] == "true"
    assert "runAsUser" not in manifest["spec"]["template"]["spec"]["securityContext"]


def test_a_mount_outside_the_workspace_is_refused(tmp_path):
    with pytest.raises(ValueError):
        job_manifest(job(mounts=[Mount("/src", path=Path("/elsewhere/repo"))]),
                     namespace="n", workspace=tmp_path, claim="c", name="x")


class FakeCluster:
    """Records what the runner sends and answers like the Kubernetes API."""

    def __init__(self, final_status):
        self.final_status = final_status
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(201, json={})
        if request.method == "DELETE":
            return httpx.Response(200, json={})
        if request.url.path.endswith("/log"):
            return httpx.Response(200, text="semgrep: rule file missing")
        if "/pods" in request.url.path:
            return httpx.Response(200, json={"items": [{"metadata": {"name": "demo-pod"}}]})
        return httpx.Response(200, json={"status": self.final_status})


def cluster_runner(cluster, tmp_path):
    client = httpx.Client(base_url="https://k8s", transport=httpx.MockTransport(cluster))
    return KubernetesRunner(client, "sentinel-scans", tmp_path, "sentinel-workspace",
                            sleep=lambda s: None, poll_seconds=0)


def test_a_finished_job_is_deleted_and_is_not_an_error(tmp_path):
    cluster = FakeCluster({"succeeded": 1})
    cluster_runner(cluster, tmp_path).run(job(mounts=[Mount("/src", path=tmp_path / "repo")]))
    methods = [m for m, _ in cluster.requests]
    assert methods[0] == "POST" and methods[-1] == "DELETE"


def test_a_failed_job_says_why_and_is_still_deleted(tmp_path):
    cluster = FakeCluster({"failed": 1})
    with pytest.raises(ScanJobError, match="rule file missing"):
        cluster_runner(cluster, tmp_path).run(job(mounts=[Mount("/src", path=tmp_path / "repo")]))
    assert cluster.requests[-1][0] == "DELETE"


def test_the_token_is_read_again_on_every_request(tmp_path):
    token = tmp_path / "token"
    token.write_text("first\n")
    seen = []

    def handler(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(200, json={})

    client = httpx.Client(base_url="https://k8s", transport=httpx.MockTransport(handler),
                          auth=ServiceAccountAuth(token))
    client.get("/x")
    token.write_text("second\n")  # kubelet rotated the projected token
    client.get("/x")
    assert seen == ["Bearer first", "Bearer second"]


def test_scratch_dir_is_removed_and_read_result_handles_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_WORKSPACE", str(tmp_path))
    with scratch_dir("sentinel-test-") as out:
        assert out.parent == tmp_path and out.is_dir()
        assert read_result(out / "result.json") is None
        (out / "result.json").write_text('{"ok": true}')
        assert read_result(out / "result.json") == {"ok": True}
    assert not out.exists()


def test_run_job_uses_docker_unless_told_otherwise(monkeypatch):
    calls = []
    monkeypatch.setattr(runner.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or
                        __import__("subprocess").CompletedProcess(cmd, 0, stdout="", stderr=""))
    monkeypatch.delenv("SENTINEL_RUNNER", raising=False)
    runner._runner.cache_clear()
    runner.run_job(job())
    assert calls and calls[0][:2] == ["docker", "run"]
    runner._runner.cache_clear()


def test_memory_is_written_in_kubernetes_units():
    assert k8s_memory("1g") == "1Gi" and k8s_memory("256m") == "256Mi" and k8s_memory("512K") == "512Ki"
    for bad in ("1", "1Gi", "g", "1.5g", ""):
        with pytest.raises(ValueError):
            k8s_memory(bad)


def test_scanner_jobs_run_under_gvisor_only_when_asked(tmp_path):
    def pod(**extra):
        manifest = job_manifest(job(mounts=[Mount("/src", path=tmp_path / "repo")]), namespace="sentinel-scans",
                                workspace=tmp_path, claim="sentinel-workspace", name="demo-abc", **extra)
        return manifest["spec"]["template"]["spec"]
    assert "runtimeClassName" not in pod()
    assert pod(runtime_class="gvisor")["runtimeClassName"] == "gvisor"
