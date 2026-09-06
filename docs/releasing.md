# Releasing

## Private distribution

The repository currently stays private. Build a wheel/sdist after the test and packaging gates pass; attach them to a private prerelease for collaborators. Users need repository/release access. No public PyPI release should be inferred from a private GitHub prerelease.

1. Update version in `pyproject.toml`, `src/skillstate/__init__.py` and `CITATION.cff`.
2. Update CHANGELOG and regenerate `uv.lock`.
3. Run lint, formatting, the full tests, build, `twine check`, and `scripts/check_wheel.py`.
4. Review tracked files for credentials, real task state and local paths.
5. Push the release commit; wait for the exact commit's CI matrix.
6. Tag only the verified commit; attach its distributions and checksums.

## PyPI publication

PyPI publication makes distributions publicly downloadable, even if GitHub remains private. Publication has been requested for this project; the first public candidate is 0.1.1. Registry presence and workflow results, not a prepared document, establish that publication actually happened.

The manually dispatched `.github/workflows/publish.yml` runs the full CI matrix and builds once. It uploads those artifacts to TestPyPI, downloads both distributions and verifies their SHA-256 hashes, installs the downloaded wheel in a fresh environment, then uploads the same artifacts to PyPI and repeats verification. Publishing jobs alone receive `id-token: write`; they do not check out or execute project code. `skip-existing` supports interrupted-run recovery; differing registry hashes fail verification.

Register a pending GitHub Trusted Publisher in each account's Publishing settings:

| Field | Value |
|---|---|
| PyPI project | `skillstate-kit` |
| Owner | `Atakan-Emre` |
| Repository | `skillstate-kit` |
| Workflow filename | `publish.yml` |
| Environment on TestPyPI | `testpypi` |
| Environment on PyPI | `pypi` |

The two registries use separate accounts and publisher registrations. Limit the corresponding GitHub environments to branch `main`. Do not create broad account tokens for this workflow. Only maintainers with repository access should dispatch it. New publisher registrations require an authenticated account and any PyPI-required email/2FA setup.

After publication, verify `https://pypi.org/pypi/skillstate-kit/0.1.1/json`, the exact uploaded hashes, and clean installation using `python -m pip install skillstate-kit==0.1.1`. Tag the tested release commit and update the release notes with the publishing run URL. Never reuse a published version for changed distribution bytes.

Reference: [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

No publishing token is stored here. This release does not configure or bypass account authentication. A missing publisher setup must be reported as an outstanding release prerequisite, not as a successful upload.
