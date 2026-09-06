"""Verify registry bytes match tested artifacts, then exercise the downloaded wheel."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


def fetch(url: str, limit: int = 10_000_000) -> bytes:
    with urllib.request.urlopen(url, timeout=20) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Registry response exceeded the size limit")
    return content


def main():
    index, dist_arg = sys.argv[1:]
    host = {"pypi": "pypi.org", "testpypi": "test.pypi.org"}[index]
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    expected = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in Path(dist_arg).iterdir()
        if path.name.endswith((".whl", ".tar.gz"))
    }
    if len(expected) != 2:
        raise ValueError("Expected exactly the tested wheel and source distribution")
    url = f"https://{host}/pypi/{project['name']}/{project['version']}/json"
    for attempt in range(12):
        try:
            metadata = json.loads(fetch(url))
            records = {record["filename"]: record for record in metadata["urls"]}
            if not expected.keys() <= records.keys():
                raise ValueError("Registry has not exposed every distribution yet")
            break
        except (urllib.error.URLError, ValueError):
            if attempt == 11:
                raise
            time.sleep(5)
    with tempfile.TemporaryDirectory(prefix="skillstate-index-") as directory:
        for name, checksum in expected.items():
            record = records[name]
            if record["digests"]["sha256"] != checksum or record.get("yanked"):
                raise ValueError(f"Registry digest mismatch or yanked distribution: {name}")
            parsed = urlsplit(record["url"])
            if parsed.scheme != "https" or not (parsed.hostname or "").endswith(
                ".pythonhosted.org"
            ):
                raise ValueError("Unexpected registry download host")
            data = fetch(record["url"])
            if hashlib.sha256(data).hexdigest() != checksum:
                raise ValueError(f"Downloaded digest mismatch: {name}")
            (Path(directory) / name).write_bytes(data)
        subprocess.run([sys.executable, "scripts/check_wheel.py", directory], check=True)
    print(json.dumps({"index": index, "version": project["version"], "verified": sorted(expected)}))


if __name__ == "__main__":
    main()
