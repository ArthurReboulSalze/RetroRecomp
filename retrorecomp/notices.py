"""The licence notices embedded in an exported game: one text per machine, built in one place.

A game names every third-party component compiled into it, with its licence text, and nothing else. The list is data on the
machine's profile (`SystemProfile.notice_files`, `optional_notice_files`, and the player shell's `SHELL_NOTICE_FILES`): files of
the bundle, each a stamp input of the machines that declare it only (`stamp_inputs.py` reads the same lists). Adding a
machine's notice therefore moves no other machine's stamp. `THIRD_PARTY_NOTICES.md` stays the complete public list of the
converter distribution; no game embeds it.

A machine whose engine carries more notices in its pinned checkout (a vendored library's licence file, the header of a source
file) passes those texts as `extra`: they are fixed by the engine's revision, not by a file of the bundle.
"""
from .paths import ASSETS
from .systems import get_profile

OWN_LICENCE = 'LICENSE'
NL = '\n'
HEADER = ('Retro-Recomp game executable ({name}). Licence notices of the components compiled into it; '
          'each component keeps its own terms.')


def notice_files(system_id: str, optional: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The bundle files whose text a game of this machine embeds, in order: the machine's components, the optional ones this
    game asks for (they must be declared on the profile), the player shell's."""
    profile = get_profile(system_id)
    unknown = [name for name in optional if name not in profile.optional_notice_files]
    if unknown:
        raise ValueError('Notice not declared as optional on the ' + system_id + ' profile: ' + ', '.join(unknown))
    left_out = set(profile.optional_notice_files) - set(optional)
    return tuple(name for name in profile.declared_notice_files if name not in left_out)


def _title(name: str) -> str:
    return name.removeprefix('licenses/').removesuffix('.md')


def notice_text(system_id: str, *, optional: tuple[str, ...] = (), extra=()) -> str:
    """The notice text of one game: the machine's components first (a GPL machine's terms open the text), Retro-Recomp's own
    licence, the player shell's components, then `extra`, (title, text) pairs read from the pinned engine. A declared file
    that is missing is an error: a notice is never dropped silently."""
    profile = get_profile(system_id)
    names = notice_files(system_id, optional)
    own = [name for name in names if name in profile.notice_files or name in profile.optional_notice_files]
    section = lambda title, text: '## ' + title + NL + NL + text.strip()
    read = lambda name: section(_title(name), (ASSETS / name).read_text(encoding='utf-8'))
    parts = [HEADER.format(name=profile.name), *(read(name) for name in own),
             section('Retro-Recomp', (ASSETS / OWN_LICENCE).read_text(encoding='utf-8')),
             *(read(name) for name in names if name not in own),
             *(section(title, text) for title, text in extra)]
    return (NL + NL).join(parts) + NL
