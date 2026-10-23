"""Check that relative links in the documentation point at existing files.

    python tools/check_doc_links.py            # every Markdown file of the checkout
    python tools/check_doc_links.py --public   # Git-tracked files only

Inline Markdown links, image links and HTML ``href`` attributes are checked.
Anchors are not verified. Upstream licence texts under ``licenses/`` are
skipped: their links refer to files of the original projects.

In ``--public`` mode a link from a public file to a file outside the public
allowlist is reported separately: it is not an error here, but such a link is
broken for readers of the public repository.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
INLINE = re.compile(r"\]\(<?([^)<>\s]+?)>?(?:\s+\"[^\"]*\")?\)")
HREF = re.compile(r"""href=["']([^"'#?]+)""")
SKIP_PARTS = {".build", ".deps", "Export", "licenses", "__pycache__", ".git", "site"}
LOCAL_ROOTS = ("README.md", "AGENTS.md", "CONTRIBUTING.md", "THIRD_PARTY_NOTICES.md", "docs", "native")


@dataclass
class Report:
    files: int = 0
    links: int = 0
    broken: list[tuple[str, str]] = field(default_factory=list)
    private: list[tuple[str, str]] = field(default_factory=list)


def _skipped(path: Path, root: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.relative_to(root).parts)


def markdown_files(root: Path, public: bool) -> list[Path]:
    if public:
        try:
            raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
            names = [name.decode("utf-8") for name in raw.split(b"\0") if name]
        except (OSError, subprocess.CalledProcessError):
            sys.path.insert(0, str(root))
            from tools.prepare_publication import PUBLIC_FILES
            names = list(PUBLIC_FILES)
        paths = [root / name for name in names if name.endswith(".md")]
    else:
        paths = []
        for name in LOCAL_ROOTS:
            start = root / name
            if start.is_file():
                paths.append(start)
            elif start.is_dir():
                paths.extend(sorted(start.rglob("*.md")))
    return [path for path in paths if path.is_file() and not _skipped(path, root)]


def check_links(root: Path = ROOT, public: bool = False) -> Report:
    public_set = None
    if public:
        sys.path.insert(0, str(root))
        from tools.prepare_publication import PUBLIC_SET as public_set
    report = Report()
    for path in markdown_files(root, public):
        report.files += 1
        text = path.read_text(encoding="utf-8")
        for target in INLINE.findall(text) + HREF.findall(text):
            if "://" in target or target.startswith(("mailto:", "#")):
                continue
            clean = target.split("#", 1)[0].split("?", 1)[0]
            if not clean:
                continue
            report.links += 1
            resolved = path.parent / clean
            relative = Path(os.path.relpath(resolved.resolve(), root)).as_posix()
            source = path.relative_to(root).as_posix()
            if public_set is not None and relative not in public_set:
                report.private.append((source, target))
                continue
            if not resolved.exists():
                report.broken.append((source, target))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--public", action="store_true", help="check Git-tracked files only")
    args = parser.parse_args()
    report = check_links(args.root.resolve(), args.public)
    print(f"{report.files} files, {report.links} relative links, {len(report.broken)} broken")
    for source, target in report.broken:
        print(f"  broken: {source}: {target}")
    if report.private:
        print(f"{len(report.private)} links from public files to local-only files:")
        for source, target in report.private:
            print(f"  local-only: {source}: {target}")
    return 1 if report.broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
