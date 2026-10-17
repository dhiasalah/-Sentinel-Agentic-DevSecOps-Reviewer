"""Run one scanner container: as `docker run` on a laptop, or as a Kubernetes Job in the cluster.

The scanners never see Docker or the cluster API themselves. They describe a Job (image, command,
mounts, limits) and call run_job(). Results come back as a file in an output folder, not as stdout,
so both backends read the same thing.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import httpx

SA_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")
SCANNER_UID = "65534:65534"  # "nobody": scanners never run as root
RUNNER_ENV_KEYS = (
    "SENTINEL_RUNNER", "SENTINEL_WORKSPACE", "SENTINEL_WORKSPACE_CLAIM", "SENTINEL_K8S_NAMESPACE",
    "KUBERNETES_SERVICE_HOST", "KUBERNETES_SERVICE_PORT",
)


DOCKER_TO_K8S_UNITS = {"k": "Ki", "m": "Mi", "g": "Gi"}


def k8s_memory(value: str) -> str:
    """Docker writes memory as "1g" / "256m"; Kubernetes needs "1Gi" / "256Mi" (there "m" means milli)."""
    number, unit = value[:-1], value[-1:].lower()
    if not number.isdigit() or unit not in DOCKER_TO_K8S_UNITS:
        raise ValueError(f"memory must look like 256m or 1g, got {value!r}")
    return number + DOCKER_TO_K8S_UNITS[unit]


class ScanJobError(RuntimeError):
    """A scanner container failed, timed out, or could not be started."""


@dataclass(frozen=True)
class Mount:
    target: str                  # where the folder or file appears inside the container
    path: Path | None = None     # a folder/file under the workspace (the worker's own view)
    cache: str | None = None     # a named cache volume (Trivy's vulnerability database)
    read_only: bool = True

    def __post_init__(self) -> None:
        if (self.path is None) == (self.cache is None):
            raise ValueError("a mount needs exactly one of path or cache")


@dataclass(frozen=True)
class Job:
    name: str                    # short tool name ("semgrep"), used in Kubernetes object names
    image: str                   # always pinned by digest
    args: list[str]
    mounts: list[Mount]
    timeout: int = 300
    network: bool = False        # scanners: no network. Only rule/database downloads need it
    read_only: bool = True       # read-only root filesystem, /tmp in memory
    user: str | None = SCANNER_UID  # None = the image's own user (only the Trivy DB updater)
    memory: str | None = "1g"
    cpus: str | None = "1"
    pids: int | None = 256       # Docker only: Kubernetes has no per-pod pid limit
    env: dict[str, str] = field(default_factory=dict)


# ---------- Docker backend (laptop) ----------

def docker_command(job: Job) -> list[str]:
    cmd = ["docker", "run", "--rm", "--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
    if not job.network:
        cmd += ["--network", "none"]
    if job.read_only:
        cmd += ["--read-only", "--tmpfs", "/tmp"]
    if job.user:
        cmd += ["--user", job.user]
    if job.memory:
        cmd += ["--memory", job.memory]
    if job.cpus:
        cmd += ["--cpus", job.cpus]
    if job.pids:
        cmd += ["--pids-limit", str(job.pids)]
    for key, value in job.env.items():
        cmd += ["-e", f"{key}={value}"]
    for mount in job.mounts:
        source = str(mount.path.resolve()) if mount.path else mount.cache
        cmd += ["-v", f"{source}:{mount.target}" + (":ro" if mount.read_only else "")]
    return [*cmd, job.image, *job.args]


class DockerRunner:
    def run(self, job: Job) -> None:
        proc = subprocess.run(docker_command(job), capture_output=True, encoding="utf-8", timeout=job.timeout + 60)
        if proc.returncode != 0:
            raise ScanJobError(f"{job.name} failed (exit {proc.returncode}): {proc.stderr[-500:]}")


# ---------- Kubernetes backend (cluster) ----------

def job_manifest(job: Job, *, namespace: str, workspace: Path, claim: str, name: str) -> dict:
    """The Kubernetes Job for one scanner run. Pure function: no cluster needed to test it."""
    volumes, mounts = [], []
    for index, mount in enumerate(job.mounts):
        volume = f"mount-{index}"
        if mount.path is not None:
            rel = mount.path.resolve().relative_to(workspace.resolve()).as_posix()
            if rel == ".":
                raise ValueError("a mount cannot be the whole workspace")
            volumes.append({"name": volume, "persistentVolumeClaim": {"claimName": claim}})
            spec = {"name": volume, "mountPath": mount.target, "subPath": rel}
        else:
            volumes.append({"name": volume, "persistentVolumeClaim": {"claimName": mount.cache}})
            spec = {"name": volume, "mountPath": mount.target}
        if mount.read_only:
            spec["readOnly"] = True
        mounts.append(spec)
    if job.read_only:
        volumes.append({"name": "tmp", "emptyDir": {"medium": "Memory", "sizeLimit": "64Mi"}})
        mounts.append({"name": "tmp", "mountPath": "/tmp"})

    limits = {}
    if job.memory:
        limits["memory"] = k8s_memory(job.memory)
    if job.cpus:
        limits["cpu"] = job.cpus
    container = {
        "name": job.name,
        "image": job.image,
        "args": job.args,
        "env": [{"name": k, "value": v} for k, v in job.env.items()],
        "volumeMounts": mounts,
        "resources": {"limits": limits, "requests": {"cpu": "100m", "memory": "128Mi"}},
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": job.read_only,
        },
    }
    pod_security = {"seccompProfile": {"type": "RuntimeDefault"}}
    if job.user:
        uid, gid = (int(part) for part in job.user.split(":"))
        pod_security |= {"runAsNonRoot": True, "runAsUser": uid, "runAsGroup": gid}
    labels = {
        "app.kubernetes.io/part-of": "sentinel",
        "app.kubernetes.io/component": "scanner",
        "sentinel.dev/tool": job.name,
        "sentinel.dev/network": "true" if job.network else "false",
    }
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": namespace, "labels": labels},
        "spec": {
            "backoffLimit": 0,                    # a failed scan is reported, never silently retried
            "activeDeadlineSeconds": job.timeout,  # hard stop
            "ttlSecondsAfterFinished": 300,        # backup cleanup if the worker dies
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,  # scanners never talk to the API
                    "securityContext": pod_security,
                    "containers": [container],
                    "volumes": volumes,
                },
            },
        },
    }


class ServiceAccountAuth(httpx.Auth):
    """Read the token on every request: projected tokens are rotated while the worker runs."""

    def __init__(self, token_path: Path):
        self.token_path = token_path

    def auth_flow(self, request):
        request.headers["Authorization"] = "Bearer " + self.token_path.read_text(encoding="utf-8").strip()
        yield request


class KubernetesRunner:
    def __init__(self, client: httpx.Client, namespace: str, workspace: Path, claim: str,
                 sleep=time.sleep, poll_seconds: float = 2.0):
        self.client = client
        self.namespace = namespace
        self.workspace = workspace
        self.claim = claim
        self.sleep = sleep
        self.poll_seconds = poll_seconds

    def run(self, job: Job) -> None:
        name = f"{job.name}-{uuid.uuid4().hex[:10]}"
        manifest = job_manifest(job, namespace=self.namespace, workspace=self.workspace,
                                claim=self.claim, name=name)
        jobs = f"/apis/batch/v1/namespaces/{self.namespace}/jobs"
        created = self.client.post(jobs, json=manifest)
        if created.is_error:
            raise ScanJobError(f"{job.name}: the cluster refused the Job ({created.status_code}): {created.text[:300]}")
        try:
            deadline = time.monotonic() + job.timeout + 60
            while True:
                status = self.client.get(f"{jobs}/{name}").raise_for_status().json().get("status", {})
                if status.get("succeeded"):
                    return
                if status.get("failed"):
                    raise ScanJobError(f"{job.name} failed: {self._logs(name)}")
                if time.monotonic() > deadline:
                    raise ScanJobError(f"{job.name} did not finish in time")
                self.sleep(self.poll_seconds)
        finally:
            self.client.delete(f"{jobs}/{name}", params={"propagationPolicy": "Background"})

    def _logs(self, job_name: str) -> str:
        pods = self.client.get(f"/api/v1/namespaces/{self.namespace}/pods",
                               params={"labelSelector": f"job-name={job_name}"}).json().get("items", [])
        if not pods:
            return "no pod was created"
        pod = pods[0]["metadata"]["name"]
        text = self.client.get(f"/api/v1/namespaces/{self.namespace}/pods/{pod}/log",
                               params={"tailLines": 40}).text
        return text[-500:]


def in_cluster_client() -> httpx.Client:
    host = os.environ["KUBERNETES_SERVICE_HOST"]
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    return httpx.Client(
        base_url=f"https://{host}:{port}",
        auth=ServiceAccountAuth(SA_DIR / "token"),
        verify=str(SA_DIR / "ca.crt"),
        timeout=30,
    )


# ---------- choosing the backend and the workspace ----------

def workspace_root() -> Path:
    """Where checkouts, outputs and sandbox copies live. In the cluster this is the shared volume."""
    return Path(os.environ.get("SENTINEL_WORKSPACE") or tempfile.gettempdir())


@lru_cache(maxsize=1)
def _runner():
    if os.environ.get("SENTINEL_RUNNER", "docker") != "kubernetes":
        return DockerRunner()
    namespace = os.environ.get("SENTINEL_K8S_NAMESPACE") or (SA_DIR / "namespace").read_text().strip()
    claim = os.environ["SENTINEL_WORKSPACE_CLAIM"]
    return KubernetesRunner(in_cluster_client(), namespace, workspace_root(), claim)


def run_job(job: Job) -> None:
    _runner().run(job)


@contextmanager
def scratch_dir(prefix: str) -> Iterator[Path]:
    """A folder for one scan's output (and staged config). Writable by the scanner user, removed afterwards."""
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=workspace_root()))
    os.chmod(path, 0o777)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def read_result(path: Path) -> object | None:
    """The scanner's JSON result file, or None when the scanner wrote none (nothing found)."""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
