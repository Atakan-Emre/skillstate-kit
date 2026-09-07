# Releasing

## Release preparation

The repository is public and MIT licensed. Build a wheel/sdist after the test and packaging gates pass; attach the verified distributions to the GitHub release. Alpha versions can be marked as prereleases. A GitHub release does not by itself establish that the package has been published on PyPI.

1. Update version in `pyproject.toml`, `src/skillstate/__init__.py` and `CITATION.cff`.
2. Update CHANGELOG and regenerate `uv.lock`.
3. Run lint, formatting, the full tests, build, `twine check`, and `scripts/check_wheel.py`.
4. Review tracked files for credentials, real task state and local paths.
5. Push the release commit; wait for the exact commit's CI matrix.
6. Tag only the verified commit; attach its distributions and checksums.

## PyPI publication

Version 0.1.2 is published on PyPI; see [release evidence](releases/0.1.2.md). Registry presence and workflow results, not a prepared document, establish that a new publication actually happened.

The manually dispatched `.github/workflows/publish.yml` runs the full CI matrix, builds once and verifies a clean wheel installation before uploading to PyPI. It then downloads both published distributions, verifies their SHA-256 hashes against the tested artifacts and exercises the downloaded wheel in a fresh environment. Publishing jobs alone receive `id-token: write`; they do not check out or execute project code. `skip-existing` supports interrupted-run recovery; differing registry hashes fail verification.

The optional `testpypi` input adds a rehearsal before production using the same artifacts and hash/installation verification. It requires a separate TestPyPI account and publisher. The initial public release uses the production route after local and CI validation; TestPyPI availability is not a prerequisite. A requested rehearsal that fails blocks production.

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

After publication, verify the version-specific PyPI JSON endpoint (for example, `https://pypi.org/pypi/skillstate-kit/0.1.2/json`), the exact uploaded hashes, and clean installation using `python -m pip install skillstate-kit==0.1.2`, substituting the version being released. Tag the tested release commit and update the release notes with the publishing run URL. Never reuse a published version for changed distribution bytes.

Reference: [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

No publishing token is stored here. This release does not configure or bypass account authentication. A missing publisher setup must be reported as an outstanding release prerequisite, not as a successful upload.
