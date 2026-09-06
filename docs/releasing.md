# Releasing

## Private distribution

The repository currently stays private. Build a wheel/sdist after the test and packaging gates pass; attach them to a private prerelease for collaborators. Users need repository/release access. No public PyPI release should be inferred from a private GitHub prerelease.

1. Update version in `pyproject.toml`, `src/skillstate/__init__.py` and `CITATION.cff`.
2. Update CHANGELOG and regenerate `uv.lock`.
3. Run lint, formatting, the full tests, build, `twine check`, and `scripts/check_wheel.py`.
4. Review tracked files for credentials, real task state and local paths.
5. Push the release commit; wait for the exact commit's CI matrix.
6. Tag only the verified commit; attach its distributions and checksums.

## Future PyPI publication

PyPI publication makes distributions publicly downloadable, even if GitHub remains private. Confirm that publication is intended, verify the chosen name, configure a protected publishing environment and Trusted Publishing, then validate on TestPyPI before production PyPI.

No publishing token is stored here. This release does not configure or bypass account authentication. A missing publisher setup must be reported as an outstanding release prerequisite, not as a successful upload.
