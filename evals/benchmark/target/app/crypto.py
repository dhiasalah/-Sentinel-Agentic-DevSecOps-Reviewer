import hashlib
import random
import string

SECRET_KEY = "s3nt1nel-benchmark-not-a-real-secret"


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def reset_token() -> str:
    return "".join(random.choice(string.ascii_letters) for _ in range(32))


def file_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
