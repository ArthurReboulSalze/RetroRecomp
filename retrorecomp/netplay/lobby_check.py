"""The lobby's game check: does this PC hold the game the host chose, and the same version of it?

The host's side turns the report of its own compiled game into a `control.Game` (`game_from_report`); each guest turns the
reports of ITS OWN compiled games of the same machine and dump into the same shape and compares (`compare`). Both read the
converter's own inventory (`compiled_games.Inventory`, the `compiled-games.json` of the data folder, or a scratch one in tests)
and the conversion reports it names (`compiled_games.read_json`); nothing is converted, nothing is written, nothing is
executed, and no path, file name or command line ever goes on the wire: the answer carries a status, reason bits and a
converter version, and the guest's converter keeps the executable it found for the launch.

What is compared (`control.Game`):

* always: the machine, the dump's SHA-256 (how a guest finds its candidates), the converter version of the export, the engine
  content part of the simulation identity, the run-changing options, the firmware identity the report names, and the
  simulation identity's schema number;
* the generated sources (which hold what the player's own learned paths made the converter write) only in MODE_FULL. A machine
  is MODE_PORTABLE when its mixed-build gate passed: two exports of one dump with different learned paths computed the same
  frames from power-on and across a quick state (`PORTABLE_MACHINES`). Anywhere else the full simulation identity is compared
  and the reconversion with the host's paths (`netplay_recipe`) is the fallback, which stays dormant: the check only says
  "reconvert" and which part differs.

A guest never trusts the host's claim about the mode: it compares in the stricter of the two (its own table, and the host's
mode), so a host that calls a machine portable when this converter does not, or that sends no sources, gets "other version".

Answers: `CHECK_SAME` ("same game"), `CHECK_OTHER` ("same game, other version (reconvert: ...)", with the reason bits of
`REASONS`) and `CHECK_MISSING` ("not found (needs <title>, SHA-256 ...)"); `CHECK_FAILED` is the guest's way of saying it could
not look at all. The English lines (`CheckAnswer.text`) are for logs and tests: the window words each answer from its fields.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from . import control, seat_map
from .control import CHECK_FAILED, CHECK_MISSING, CHECK_OTHER, CHECK_SAME, MODE_FULL, MODE_PORTABLE

# The machines whose MIXED-BUILD GATE passed: two exports of one dump that differ only by their learned paths compute the same
# frames from power-on (and, for the first two, after a quick-state round trip), so the lobby compares them without the learned
# paths and nobody recompiles. Evidence: .build/multiplayer/MIXED_BUILD_GATE.md (NES: Battletoads-Double Dragon; Mega Drive:
# Sonic The Hedgehog 2; Master System: Gauntlet, from power-on, its quick-state part not run). The Game Gear shares the Master
# System's engine but was not run: it is compared in full. This is data of the netplay package and not of the machine
# profiles on purpose: a profile field would move the game stamp of every game of the machine. Raise it only with a passed gate.
PORTABLE_MACHINES = frozenset(('nes', 'md', 'sms'))

# The players one machine offers in a room (STUDY.md section 3, the adapters' players); the host's window may name fewer, never more
# than four. A machine with 1 has no second player: the lobby refuses to pick it in "one controller per player", and the
# handhelds (`seat_map.HANDHELDS`) play in input sharing, whose seats all drive the same controls (up to four). The CPS boards say
# 4 here, the most a board has: the number of THIS game is what its own HELLO reports (`session_pipe.check_hello` refuses more
# seats than the game has players) and, when the conversion report says it (`players_in_report`), what the report says.
# `scummvm` has 1 and is not a handheld: a point-and-click game is not a pad game.
MACHINE_SEATS = {'sms': 2, 'gg': 1, 'gb': 1, 'nes': 2, 'md': 2, 'snes': 2, 'ng': 2, 'x68': 2, 'cps1': 4, 'cps2': 4, 'pce': 2,
                 'gba': 1, 'amiga': 2, 'a1200': 2, 'atarist': 2, 'n64': 4, 'scummvm': 1, 'psx': 2, 'msx': 2, 'msx2': 2,
                 'msx2plus': 2}

CEILING_MACHINES = frozenset(('cps1', 'cps2'))     # MACHINE_SEATS is the most a board has; the report and the HELLO say the game's

R_CONVERTER, R_ENGINE, R_OPTIONS, R_SOURCES, R_FIRMWARE, R_SCHEMA, R_NO_IDENTITY = 1, 2, 4, 8, 16, 32, 64
REASONS = {R_CONVERTER: 'converter version', R_ENGINE: 'engine', R_OPTIONS: 'options', R_SOURCES: 'learned paths',
           R_FIRMWARE: 'firmware', R_SCHEMA: 'identity rules', R_NO_IDENTITY: 'no simulation identity'}
# Where a report names the firmware it was converted with: top-level keys holding a record with a `sha256` (Neo Geo and
# PlayStation write `bios`). A machine whose report names none has its firmware, if any, inside the generated sources.
FIRMWARE_KEYS = ('bios', 'firmware', 'bios_source', 'kickstart', 'tos')
ZERO = bytes(32)
_HEX = re.compile(r'[0-9a-f]{64}')
_VERSION = re.compile(r'(\d{1,5})\.(\d{1,5})\.(\d{1,5})')


_PLAYERS_OF_BOARD = re.compile(r'players 1 to ([1-4])(?!\d)')


def players_in_report(raw: dict) -> int | None:
    """The players a CPS board's game offers controls for, as its conversion report says (`qualification_scope.controls`, "players
    1 to N", written from the catalogue's input table), or None when the report does not say. Only for the machines whose table
    value is a ceiling and not a number (`CEILING_MACHINES`); the game's own HELLO has the last word."""
    system = raw.get('system') if isinstance(raw, dict) else None
    scope = raw.get('qualification_scope') if isinstance(raw, dict) else None
    controls = scope.get('controls') if isinstance(scope, dict) else None
    if not isinstance(system, dict) or system.get('id') not in CEILING_MACHINES or not isinstance(controls, str):
        return None
    found = _PLAYERS_OF_BOARD.search(controls)
    return max(2, int(found.group(1))) if found else None


def reason_names(bits: int) -> list[str]:
    return [name for bit, name in REASONS.items() if bits & bit]


def parse_version(text) -> tuple | None:
    """'1.7.9' as (1, 7, 9); a text that is not three numbers (a development build) is None: it is compared as unknown."""
    found = _VERSION.fullmatch(text.strip()) if isinstance(text, str) else None
    return tuple(int(part) for part in found.groups()) if found and all(int(part) <= 0xffff for part in found.groups()) else None


def mode_for(machine: str) -> int:
    return MODE_PORTABLE if machine in PORTABLE_MACHINES else MODE_FULL


def _digest(value) -> bytes | None:
    return bytes.fromhex(value) if isinstance(value, str) and _HEX.fullmatch(value) else None


def firmware_digest(raw: dict) -> bytes:
    """One digest of the firmware identities a report names (`FIRMWARE_KEYS`), or 32 zero bytes when it names none."""
    found = {}
    for key in FIRMWARE_KEYS:
        value = raw.get(key)
        if isinstance(value, dict) and _digest(value.get('sha256')) is not None:
            found[key] = value['sha256']
    if not found:
        return ZERO
    return hashlib.sha256(json.dumps(found, sort_keys=True, separators=(',', ':')).encode('ascii')).digest()


def options_digest(options) -> bytes | None:
    if not isinstance(options, dict):
        return None
    try:
        text = json.dumps(options, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(b'lobby-options\0' + text.encode('ascii')).digest()


def clean_title(title, machine: str) -> str:
    from .lobby import clean_chat
    line = clean_chat(title if isinstance(title, str) else '', 64)
    while len(line.encode('utf-8')) > control.MAX_TITLE_BYTES:
        line = line[:-1].rstrip()
    return line or machine


@dataclass(frozen=True)
class Candidate:
    """What one report says about its game: the comparable `game`, or None with `reason` (a sentence for a log)."""
    game: control.Game | None
    reason: str = ''
    version: tuple = (0, 0, 0)


def game_from_report(raw, title: str = '', *, seats_max: int | None = None, game_options: str = '') -> Candidate:
    """The comparable game of one conversion report (the JSON a conversion wrote, already read). Never raises on a report that
    lacks something: it answers `Candidate(None, why)`, and a report that lacks the identity is one to reconvert."""
    from .. import simulation_identity
    if not isinstance(raw, dict):
        return Candidate(None, 'the report is not a record')
    system = raw.get('system')
    machine = system.get('id') if isinstance(system, dict) else None
    version = parse_version(raw.get('version'))
    if not isinstance(machine, str) or not control._MACHINE.fullmatch(machine):
        return Candidate(None, 'the report names no machine')
    if version is None:
        return Candidate(None, 'the report does not name the converter version of the export')
    record = raw.get('simulation_identity')
    if not isinstance(record, dict) or record.get('schema') != simulation_identity.SCHEMA:
        return Candidate(None, 'the export carries no simulation identity (reconvert it with this version)', version)
    rom_record, rom = raw.get('rom'), _digest(record.get('rom'))
    engine = record.get('engine')
    engine = _digest(engine.get('sha256')) if isinstance(engine, dict) else None
    options = options_digest(record.get('options'))
    if rom is None or engine is None or options is None or not isinstance(rom_record, dict) or rom_record.get('sha256') != rom.hex():
        return Candidate(None, record.get('reason') or 'the simulation identity is incomplete', version)
    sources = record.get('sources')
    sources = _digest(sources.get('sha256')) if isinstance(sources, dict) else None
    mode = mode_for(machine)
    if mode == MODE_FULL and (sources is None or not isinstance(record.get('identity'), str)):
        return Candidate(None, record.get('reason') or 'the export has no identity of its generated sources', version)
    seats = min(control.MAX_SEATS, (players_in_report(raw) or MACHINE_SEATS.get(machine, 1)) if seats_max is None else seats_max)
    return Candidate(control.Game(mode, simulation_identity.SCHEMA, seats, machine, version, rom, engine, options, sources or ZERO,
                                  firmware_digest(raw), clean_title(title or raw.get('title'), machine), game_options), '', version)


def compare(host: control.Game, mine: control.Game) -> int:
    """The reason bits that make `mine` another version of the host's game (0: the same game). Machine and dump are what
    found `mine`, so they are not compared here."""
    reasons = 0
    for bit, same in ((R_SCHEMA, host.schema == mine.schema), (R_CONVERTER, host.converter == mine.converter),
                      (R_ENGINE, host.engine == mine.engine), (R_OPTIONS, host.options == mine.options),
                      (R_FIRMWARE, host.firmware == mine.firmware)):
        if not same:
            reasons |= bit
    if (host.mode == MODE_FULL or mine.mode == MODE_FULL) and host.sources != mine.sources:
        reasons |= R_SOURCES
    return reasons


@dataclass(frozen=True)
class CheckAnswer:
    status: int
    reasons: int = 0
    version: tuple = (0, 0, 0)
    found: object = None            # the inventory entry (a `compiled_games.Game`) this PC would launch; never sent
    text: str = ''


class LocalLibrary:
    """This PC's compiled games as the converter's inventory knows them. `inventory` is a `compiled_games.Inventory`: the real
    one in the product, a scratch one in tests (`Inventory(path)` reads only that path)."""

    def __init__(self, inventory):
        self.inventory = inventory

    def _read(self, entry) -> dict | None:
        from ..compiled_games import read_json
        try:
            if not entry.report or not Path(entry.executable).is_file():
                return None
            return read_json(entry.report)
        except (OSError, ValueError, TypeError):
            return None

    def candidates(self, machine: str, rom: str) -> list:
        """(inventory entry, Candidate) of every export of that dump on this machine whose executable is still there."""
        found = []
        for entry in self.inventory.snapshot():
            if entry.system != machine or entry.identity != rom:
                continue
            raw = self._read(entry)
            if raw is not None:
                found.append((entry, game_from_report(raw, entry.title)))
        return sorted(found, key=lambda item: -item[0].modified)

    def check(self, game: control.Game) -> CheckAnswer:
        """The answer to the host's pick, from this PC's own exports of the same dump."""
        from .lobby import check_text
        found = self.candidates(game.machine, game.rom.hex())
        if not found:
            return CheckAnswer(CHECK_MISSING, text=check_text(game, CHECK_MISSING))
        best = None
        for entry, candidate in found:
            if candidate.game is None:
                outcome = (R_NO_IDENTITY, entry, candidate.version)
            else:
                outcome = (compare(game, candidate.game), entry, candidate.version)
            if best is None or bin(outcome[0]).count('1') < bin(best[0]).count('1'):
                best = outcome            # the first of equals is the newest export
            if outcome[0] == 0:
                break
        reasons, entry, version = best
        status = CHECK_SAME if reasons == 0 else CHECK_OTHER
        return CheckAnswer(status, reasons, version, entry, check_text(game, status, reasons, version))

    def hostable(self) -> list:
        """(inventory entry, control.Game) of every export that could be picked as the host: a second player, an identity."""
        games = []
        for entry in self.inventory.snapshot():
            raw = self._read(entry)
            candidate = game_from_report(raw, entry.title) if raw is not None else None
            if candidate is not None and candidate.game is not None and (candidate.game.seats_max >= 2 or seat_map.forced(candidate.game.machine)):
                games.append((entry, candidate.game))
        return games

    def game_of(self, entry, game_options: str = '') -> Candidate:
        """The comparable game of one inventory entry (the host's pick), with the options the host pushes."""
        raw = self._read(entry)
        if raw is None:
            return Candidate(None, 'the report or the executable of this game cannot be read')
        return game_from_report(raw, entry.title, game_options=game_options)


def game_config(entry) -> dict:
    """What the worker needs to start an inventory entry's game: its executable and its folder (the window may add the
    environment and log files, as the converter's own launcher does)."""
    path = Path(entry.executable)
    return {'exe': str(path), 'cwd': str(path.parent)}
