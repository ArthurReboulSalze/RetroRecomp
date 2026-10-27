"""ROM-free lint: every console's status (experimental or supported) must agree.

Compares the profile attribute (``retrorecomp/systems``), the README console
support table, ``docs/COMPATIBILITY.md``, the latest ``docs/RELEASE_NOTES.md``
section and the interface strings (``retrorecomp/i18n.py`` and
``assets/locales/*.json``) that mention experimental consoles. Prints one row
per console and exits 1 on a contradiction. It also reports the drift items of
the 27 October 2026 pipeline inventory (section 5.4) that can be detected
mechanically; drift items never change the exit code.

    python -B tools/status_lint.py
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

CONSOLES = (
    ("sms", "Master System"),
    ("gg", "Game Gear"),
    ("gb", "Game Boy"),
    ("nes", "Nintendo NES"),
    ("md", "Mega Drive"),
    ("snes", "Super Nintendo"),
    ("ng", "Neo Geo"),
    ("cps1", "Capcom CPS-1"),
    ("x68", "Sharp X68000"),
)

ALIASES = {
    "sms": ("Master System",),
    "gg": ("Game Gear",),
    "gb": ("Game Boy",),
    "nes": ("Nintendo NES", "NES"),
    "md": ("Mega Drive",),
    "snes": ("Super Nintendo", "SNES"),
    "ng": ("Neo Geo",),
    "cps1": ("CPS-1",),
    "x68": ("X68000",),
}

# Interface keywords that say "experimental" in the shipped languages. Only
# experimental statements are detected: a supported claim in the interface is
# the absence of these keywords, which is never a contradiction by itself.
EXPERIMENTAL_KEYWORDS = {
    "en": ("experimental",),
    "fr": ("expérimental",),
    "de": ("experimentell",),
    "es": ("experimental",),
    "it": ("sperimentale",),
    "ja": ("実験",),
    "ru": ("эксперимент",),
    "zh": ("实验",),
}

_NEGATED_EXPERIMENTAL = ("no longer experimental", "leaves experimental status")
_EXPERIMENTAL_RE = re.compile(r"experimental", re.IGNORECASE)
_SUPPORTED_RE = re.compile(r"\bsupports?\b|\bsupported\b", re.IGNORECASE)
# A colon is not a sentence border: "Experimental profile: DIM/XDF" states the
# console status across it.
_SENTENCE_SPLIT = re.compile(r"(?<=[.;!?])\s+")


def alias_pattern(console_id: str) -> re.Pattern[str]:
    names = "|".join(re.escape(alias) for alias in ALIASES[console_id])
    return re.compile(rf"\b(?:{names})\b")


def sentence_status(sentence: str) -> str | None:
    """Status word a sentence states, or None ('unsupported' states nothing)."""
    low = sentence.casefold()
    for negated in _NEGATED_EXPERIMENTAL:
        if negated in low:
            return "supported"
    if _EXPERIMENTAL_RE.search(low):
        return "experimental"
    if _SUPPORTED_RE.search(low):
        return "supported"
    return None


def iter_sentences(text: str):
    """Sentence-like segments; a Markdown table row stays one unit."""
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        units = lines if lines and all(line.startswith("|") for line in lines) else [" ".join(lines)]
        for unit in units:
            for sentence in _SENTENCE_SPLIT.split(unit):
                if sentence:
                    yield sentence


def collect_prose(text: str, patterns: dict[str, re.Pattern[str]]) -> dict[str, set[str]]:
    statements: dict[str, set[str]] = {}
    for sentence in iter_sentences(text):
        status = sentence_status(sentence)
        if status is None:
            continue
        for console_id, pattern in patterns.items():
            if pattern.search(sentence):
                statements.setdefault(console_id, set()).add(status)
    return statements


def collect_interface(pairs, patterns: dict[str, re.Pattern[str]]) -> dict[str, set[str]]:
    """pairs yield (language, key, text); only experimental claims are counted."""
    statements: dict[str, set[str]] = {}
    for language, _key, text in pairs:
        keywords = EXPERIMENTAL_KEYWORDS.get(language)
        if not keywords:
            continue
        # A console is called experimental only when the alias and the keyword
        # share one sentence: one string may mix shared consoles and a note
        # about the experimental ones (for example knowledge_scope).
        for sentence in iter_sentences(text):
            low = sentence.casefold()
            if not any(keyword in low for keyword in keywords):
                continue
            for console_id, pattern in patterns.items():
                if pattern.search(sentence):
                    statements.setdefault(console_id, set()).add("experimental")
    return statements


def readme_section(readme_text: str, heading: str = "## Console support") -> str:
    start = readme_text.find(heading)
    if start < 0:
        return ""
    rest = readme_text[start + len(heading):]
    following = re.search(r"\n## ", rest)
    return rest[:following.start()] if following else rest


def latest_release_section(notes_text: str) -> str:
    headings = list(re.finditer(r"^# RetroRecomp[^\n]*", notes_text, re.M))
    if not headings:
        return ""
    end = headings[1].start() if len(headings) > 1 else len(notes_text)
    return notes_text[headings[0].start():end]


def interface_pairs(root: Path):
    from retrorecomp import i18n
    for key, value in i18n.STRINGS.items():
        if isinstance(value, tuple) and value:
            yield "en", key, str(value[0])
            if len(value) > 1:
                yield "fr", key, str(value[1])
    for path in sorted((root / "assets" / "locales").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, text in data.items():
            if isinstance(text, str):
                yield path.stem, key, text


def _display(statuses: set[str] | None) -> str:
    return ", ".join(sorted(statuses)) if statuses else "-"


def lint_data(profile_attrs: dict, readme_text: str, compatibility_text: str,
              release_notes_text: str, interface_pair_list) -> "LintResult":
    """Lint synthetic texts; profile_attrs maps console id -> experimental attr."""
    patterns = {console_id: alias_pattern(console_id) for console_id, _ in CONSOLES}
    readme = collect_prose(readme_section(readme_text), patterns)
    compatibility = collect_prose(compatibility_text, patterns)
    release = collect_prose(release_notes_text, patterns)
    interface = collect_interface(interface_pair_list, patterns)
    rows, contradictions = [], []
    for console_id, name in CONSOLES:
        attr = profile_attrs.get(console_id)
        expected = "experimental" if attr else "supported"
        profile_label = ("experimental" if attr is True
                         else "supported" if attr is False else "absent -> supported?")
        rows.append({"id": console_id, "name": name, "profile": profile_label,
                     "readme": _display(readme.get(console_id)),
                     "compatibility": _display(compatibility.get(console_id)),
                     "release_notes": _display(release.get(console_id)),
                     "interface": _display(interface.get(console_id))})
        sources = (("README", readme), ("docs/COMPATIBILITY.md", compatibility),
                   ("docs/RELEASE_NOTES.md (latest)", release), ("interface strings", interface))
        for source, statements in sources:
            for status in sorted(statements.get(console_id, ())):
                if status != expected:
                    contradictions.append(
                        f"{name}: {source} says '{status}' but the profile says '{expected}'.")
    return LintResult(rows=rows, contradictions=contradictions)


def drift_items(root: Path, profiles, main_profiles, experimental_profiles,
                compatibility_text: str) -> list[str]:
    """Mechanically detectable drift from the pipeline inventory (section 5.4)."""
    items = []
    absent = sorted(p.id for p in profiles if getattr(p, "experimental", None) is None)
    if absent:
        items.append("profile.experimental attribute is absent on: " + ", ".join(absent)
                     + " (supported only by convention while the docs agree)")
    declared = {p.id for p in main_profiles if getattr(p, "experimental", False) is True}
    members = {p.id for p in experimental_profiles}
    missing = sorted(declared - members)
    if missing:
        items.append("experimental profiles registered in PROFILES but absent from "
                     "EXPERIMENTAL_PROFILES: " + ", ".join(missing))
    unnamed = [name for console_id, name in CONSOLES
               if not alias_pattern(console_id).search(compatibility_text)]
    if unnamed:
        items.append("docs/COMPATIBILITY.md never names: " + ", ".join(unnamed))
    systems_init = (root / "retrorecomp" / "systems" / "__init__.py").read_text(encoding="utf-8")
    if "development SDK" in systems_init:
        items.append("the X68000 availability error says 'development SDK' while the docs "
                     "call the profile experimental (retrorecomp/systems/__init__.py)")
    source_uses = sum(len(re.findall(r"allow_experimental", path.read_text(encoding="utf-8")))
                      for path in (root / "retrorecomp").rglob("*.py"))
    test_uses = sum(len(re.findall(r"allow_experimental", path.read_text(encoding="utf-8")))
                    for path in (root / "tests").glob("*.py"))
    if source_uses <= 1 and test_uses:
        items.append(f"profile_for_path's allow_experimental parameter is never read in "
                     f"retrorecomp/ while tests pass it {test_uses} time(s)")
    return items


@dataclass
class LintResult:
    rows: list[dict]
    contradictions: list[str]
    drift: list[str] = field(default_factory=list)


def lint(root: Path = ROOT) -> LintResult:
    sys.path.insert(0, str(root))
    from retrorecomp.systems import PROFILES, X68000, EXPERIMENTAL_PROFILES
    profiles = list(PROFILES) + [X68000]
    attrs = {p.id: getattr(p, "experimental", None) for p in profiles}
    compatibility_text = (root / "docs" / "COMPATIBILITY.md").read_text(encoding="utf-8")
    readme_text = (root / "README.md").read_text(encoding="utf-8")
    notes_text = (root / "docs" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    result = lint_data(attrs, readme_text, compatibility_text,
                       latest_release_section(notes_text), list(interface_pairs(root)))
    result.drift = drift_items(root, profiles, PROFILES, EXPERIMENTAL_PROFILES,
                               compatibility_text)
    return result


def format_report(result: LintResult) -> str:
    headers = ("Console", "Profile", "README", "COMPATIBILITY", "RELEASE_NOTES", "Interface")
    table = [[f"{row['id']} ({row['name']})", row["profile"], row["readme"],
              row["compatibility"], row["release_notes"], row["interface"]]
             for row in result.rows]
    widths = [max(len(headers[i]), *(len(line[i]) for line in table)) for i in range(len(headers))]
    lines = ["Console status lint (ROM-free)",
             "  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)),
             "  ".join("-" * width for width in widths)]
    lines += ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line)) for line in table]
    lines.append("Legend: '-' = no statement found; 'absent -> supported?' = the profile does "
                 "not declare the experimental attribute, supported only while every source "
                 "that states a status agrees.")
    if result.drift:
        lines.append("Drift items (pipeline inventory 5.4, mechanical checks only):")
        lines += [f"  - {item}" for item in result.drift]
    else:
        lines.append("Drift items (pipeline inventory 5.4, mechanical checks only): none")
    if result.contradictions:
        lines.append("Contradictions:")
        lines += [f"  - {item}" for item in result.contradictions]
    lines.append(f"{len(result.contradictions)} contradiction(s), {len(result.drift)} drift "
                 f"item(s); exit code {1 if result.contradictions else 0}.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    args = parser.parse_args(argv)
    result = lint(args.root)
    print(format_report(result))
    return 1 if result.contradictions else 0


if __name__ == "__main__":
    sys.exit(main())
