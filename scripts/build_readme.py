"""Build the PyPI description from the canonical product README."""

import argparse
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    body = readme[readme.index("# skillstate-kit\n") :]
    base = "https://github.com/Atakan-Emre/skillstate-kit/blob/main/"
    body = re.sub(
        r"\]\(([^)]+)\)",
        lambda m: "](" + (m[1] if "://" in m[1] or m[1].startswith("#") else base + m[1]) + ")",
        body,
    )
    target = root / "docs/PYPI_README.md"
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != body:
            raise SystemExit("PyPI description is stale; run python scripts/build_readme.py")
    else:
        target.write_text(body, encoding="utf-8")


if __name__ == "__main__":
    main()
