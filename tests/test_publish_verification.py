"""The release gate must reject registry substitution before package execution."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "verify_index", Path(__file__).resolve().parents[1] / "scripts/verify_index.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.mark.parametrize("fault", [None, "metadata_hash", "download_hash", "yanked", "host"])
def test_registry_gate_rejects_substituted_distributions(tmp_path, monkeypatch, fault):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname="skillstate-kit"\nversion="0.1.1"\n')
    dist = tmp_path / "dist"
    dist.mkdir()
    records, responses = [], {}
    for suffix in (".whl", ".tar.gz"):
        name = "skillstate_kit-0.1.1" + suffix
        data = ("tested artifact " + suffix).encode()
        (dist / name).write_bytes(data)
        url = "https://test-files.pythonhosted.org/" + name
        records.append(
            {
                "filename": name,
                "url": url,
                "digests": {"sha256": hashlib.sha256(data).hexdigest()},
                "yanked": False,
            }
        )
        responses[url] = data
    if fault == "metadata_hash":
        records[0]["digests"]["sha256"] = "0" * 64
    elif fault == "download_hash":
        responses[records[0]["url"]] = b"substituted bytes"
    elif fault == "yanked":
        records[0]["yanked"] = True
    elif fault == "host":
        records[0]["url"] = "https://example.invalid/forged.whl"
    responses["https://test.pypi.org/pypi/skillstate-kit/0.1.1/json"] = json.dumps(
        {"urls": records}
    ).encode()
    executed = []
    monkeypatch.setattr(gate, "fetch", lambda url: responses[url])
    monkeypatch.setattr(gate.sys, "argv", ["verify_index.py", "testpypi", "dist"])
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **kw: executed.append(a))
    if fault:
        with pytest.raises(ValueError):
            gate.main()
        assert not executed
    else:
        gate.main()
        assert len(executed) == 1
