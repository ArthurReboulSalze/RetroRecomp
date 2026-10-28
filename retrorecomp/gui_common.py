"""Constants and small helpers shared by the interface modules."""
from __future__ import annotations

import os

from . import online
from .i18n import tr
from .systems import available_profiles
from .updater import UpdateConnectionError, UpdateServiceError
from .platforms import target_id


PROFILES = available_profiles()


LOCAL_PLATFORM = 'windows-x64' if os.name == 'nt' else target_id()
PLATFORMS = {LOCAL_PLATFORM: 'Windows version' if os.name == 'nt' else 'Linux version'}
HELP_URL = 'https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/docs/INDEX.md'
UPX_SOURCE_URL = ('https://github.com/ArthurReboulSalze/RetroRecomp/blob/'
                  '3846c13bf21575ecb9dbaecead2943f72403e5c9/licenses/upx-5.3.0-src.tar.xz')


def update_error_text(error: Exception | str, language: str) -> str:
    """Keep network diagnostics out of the player-facing update dialog."""
    if isinstance(error, UpdateConnectionError):
        return tr('update_connection_failed', language)
    if isinstance(error, UpdateServiceError):
        return tr('update_service_failed', language)
    return tr('update_failed', language, error=str(error))


UPSTREAM_CREDITS = (
    ('Master System', (
        ('mstan/smsggrecomp', 'https://github.com/mstan/smsggrecomp', 'credits_sms_recompiler'),
        ('mstan/z80-recomp-core', 'https://github.com/mstan/z80-recomp-core', 'credits_native_core'),
        ('superzazu/z80', 'https://github.com/superzazu/z80', 'credits_reference_cpu'),
    )),
    ('Game Gear', (
        ('mstan/smsggrecomp', 'https://github.com/mstan/smsggrecomp', 'credits_sms_recompiler'),
        ('mstan/z80-recomp-core', 'https://github.com/mstan/z80-recomp-core', 'credits_native_core'),
        ('superzazu/z80', 'https://github.com/superzazu/z80', 'credits_reference_cpu'),
    )),
    ('Game Boy', (
        ('arcanite24/gb-recompiled', 'https://github.com/arcanite24/gb-recompiled', 'credits_recompiler'),
    )),
    ('Nintendo NES', (
        ('mstan/nesrecomp', 'https://github.com/mstan/nesrecomp', 'credits_recompiler'),
    )),
    ('Mega Drive', (
        ('mstan/segagenesisrecomp', 'https://github.com/mstan/segagenesisrecomp', 'credits_recompiler'),
        ('mstan/m68k-recomp-core', 'https://github.com/mstan/m68k-recomp-core', 'credits_68000'),
    )),
    ('Super Nintendo', (
        ('RetroPortingToolKit/snesrecomp', 'https://github.com/RetroPortingToolKit/snesrecomp', 'credits_recompiler'),
    )),
    ('Neo Geo', (
        ('libretro/geolith-libretro', 'https://github.com/libretro/geolith-libretro', 'credits_hardware'),
        ('carmiker/lithogen', 'https://github.com/carmiker/lithogen', 'credits_cartridge_loader'),
        ('mstan/segagenesisrecomp', 'https://github.com/mstan/segagenesisrecomp', 'credits_68000'),
    )),
    ('Capcom CPS-1', (
        ('mamedev/mame', 'https://github.com/mamedev/mame', 'credits_cps1_board'),
        ('aaronsgiles/ymfm', 'https://github.com/aaronsgiles/ymfm', 'credits_cps1_sound'),
        ('libretro/geolith-libretro', 'https://github.com/libretro/geolith-libretro', 'credits_cps1_cpu'),
        ('mstan/m68k-recomp-core', 'https://github.com/mstan/m68k-recomp-core', 'credits_68000'),
    )),
    ('Sharp X68000', (
        ('hissorii/px68k', 'https://github.com/hissorii/px68k', 'credits_x68_hardware'),
        ('libretro/geolith-libretro', 'https://github.com/libretro/geolith-libretro', 'credits_x68_cpu'),
        ('mstan/segagenesisrecomp', 'https://github.com/mstan/segagenesisrecomp', 'credits_68000'),
        ('mstan/m68k-recomp-core', 'https://github.com/mstan/m68k-recomp-core', 'credits_68000'),
        ('libretro/px68k-libretro', 'https://github.com/libretro/px68k-libretro', 'credits_x68_reference'),
    )),
)


def typed_pseudonym(typed, proposed):
    """The pseudonym the sign-in sends: the field's text once the player
    changed the proposal, else None. Then the server generates one and marks it
    as generated, so the header's invitation and the pseudonym dialog still
    offer to choose one."""
    name = ' '.join(str(typed).split())
    return name if name and name != ' '.join(str(proposed).split()) else None


# Sending discoveries needs the Retro-Recomp web service (online.py); until it
# opens, the closing card offers to recompile and its Send button stays off.
SENDING_AVAILABLE = online.sending_available()
# During a long batch, new discoveries also leave every 15 minutes (one request then).
SEND_EVERY = 15 * 60
UPDATE_CHECK_EVERY = 6 * 3600   # seconds between two start-up looks for something new


def base_is_newer(info) -> bool:
    """A base check that found a published base beyond the local one."""
    return (isinstance(info, dict) and not info.get('error')
            and bool(info.get('newer')) and info.get('latest') is not None)
CLOSING_SEND = 10   # seconds a closing window waits for a send left waiting
BUSY_SEND_RETRY = 30   # seconds a waiting send waits again behind an import, export or ROM search


# Preferences that only the interface reads: never passed to a conversion. The
# Neo Geo converter refuses unknown keywords, so a key missing here fails every
# Neo Geo conversion (1.5.4 shipped `discoveries_waiting` that way); the test
# test_gui_state.InterfacePreferences checks the list against `preferences()`.
INTERFACE_PREFERENCES = ('coverage_default_revision', 'gb_validation_default_revision', 'custom_output',
                         'system_mode', 'platform', 'feedback_paths', 'rom_paths', 'send_after_batch',
                         'startup_update_check', 'last_update_check', 'discoveries_waiting',
                         # Games converted at once per console: the window cuts the queue by it.
                         'console_jobs')
