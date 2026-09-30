import os
import subprocess

UPLOAD_DIR = "/srv/uploads"


def read_upload(filename: str) -> bytes:
    with open(os.path.join(UPLOAD_DIR, filename), "rb") as f:
        return f.read()


def ping(host: str) -> str:
    return subprocess.check_output(f"ping -c 1 {host}", shell=True, text=True)


def traceroute(host: str) -> str:
    return subprocess.check_output(["traceroute", "--", host], text=True)
