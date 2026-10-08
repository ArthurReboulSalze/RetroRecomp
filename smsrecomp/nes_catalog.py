"""NES Zapper catalogue: explicit identities, then exact title aliases.

Payload CRC facts from MesenNesDB (NES/Famicom single Zapper entries),
retrieved 2026-10-08. No ROM bytes or upstream program code are included.
https://github.com/SourMesen/Mesen2/blob/master/UI/Dependencies/MesenNesDB.txt
"""
from pathlib import Path
import re
import zlib

ZAPPER_PAYLOAD_CRCS = frozenset({
    0x01B87025, 0x04A6B46D, 0x051E60C6, 0x090568DF, 0x0AFB395E, 0x0E9428FB, 0x0F263E59, 0x143DF524,
    0x19B0A9F1, 0x1BFE42AB, 0x1CA9C322, 0x1CAE8DEF, 0x1DA88F85, 0x1E6C3344, 0x1EC1DFEB, 0x1F6660E6,
    0x23D17F5E, 0x24598791, 0x27ACE333, 0x283D7727, 0x2A6559A1, 0x2CE31186, 0x2F72A0BE, 0x327DDDEC,
    0x3488A174, 0x3C04E8EF, 0x3E58A87E, 0x3E85BA0F, 0x3F8BB92D, 0x407449DA, 0x4318A2F8, 0x431A5F59,
    0x44340DA6, 0x44BEB4B0, 0x497C6A69, 0x4A3D4790, 0x4B143FB6, 0x4D3982BC, 0x4D68CFB1, 0x4E959173,
    0x4FBBFA74, 0x5112DC21, 0x522EE20F, 0x524BC479, 0x5529431F, 0x5D4574E0, 0x5E8C77DB, 0x5EE6008E,
    0x61061352, 0x62AF1BC4, 0x6332E4CA, 0x63506FB4, 0x64594DA3, 0x6519CB3B, 0x67751094, 0x70DF0D3D,
    0x73CCDAE0, 0x73FB55AC, 0x74BEA652, 0x790B295B, 0x7A018E1F, 0x7BAF8142, 0x7C4EBDAC, 0x7C899CFA,
    0x7CDF51D5, 0x7D01D4E0, 0x7FC220F7, 0x82908FF7, 0x8373021E, 0x851EB9BE, 0x8A7D9467, 0x8B7DA8B8,
    0x91467F41, 0x93216279, 0xA0FBF02E, 0xA1430EEB, 0xA39A8063, 0xA671DA25, 0xA7C6C842, 0xA7F8BBC8,
    0xAA65ADBF, 0xAA9F9765, 0xB037246D, 0xB0480AE9, 0xB133CFA7, 0xB8B9ACA3, 0xBBE40DC4, 0xBC9BFFCB,
    0xBCFDD7DE, 0xBEB8AB01, 0xC0F0D838, 0xC267D861, 0xC3C9D852, 0xC49F6407, 0xC616BAD5, 0xCA2C23E2,
    0xCFD8D4A5, 0xD0FBE052, 0xD5BCF1E5, 0xD7CD7E8E, 0xDDCBDA16, 0xDE8FD935, 0xDF31B364, 0xDF3E45D2,
    0xE145B441, 0xE18CD9AA, 0xE615C8DF, 0xEDC3662B, 0xF24C0B66, 0xF27F9E88, 0xF4E7A58C, 0xF5E62944,
    0xFA08CCBF, 0xFF24D794,
})

ZAPPER_TITLES = (
    "Duck Hunt", "Hogan's Alley", "Wild Gunman", "Gumshoe",
    "Barker Bill's Trick Shooting", "To the Earth", "Freedom Force",
    "Laser Invasion", "LaserScope", "Operation Wolf", "Mechanized Attack",
    "The Adventures of Bayou Billy", "Adventures of Bayou Billy, The",
    "Mad City", "Gotcha! The Sport!", "Shooting Range", "Track & Field II",
    "Baby Boomer", "Chiller", "Super Mario Bros. + Duck Hunt",
    "Super Mario Bros. + Duck Hunt + World Class Track Meet",
)

def _title(value: str) -> str:
    name = Path(value).name
    if Path(name).suffix.casefold() in {'.nes', '.zip', '.bin', '.rom'}:
        name = Path(name).stem
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\([^)]*\)|\[[^]]*\]", "", name).casefold())

def zapper_game(data: bytes, filename: str) -> bool:
    if len(data) < 16 or data[:4] != b"NES\x1a":
        return False
    if data[7] & 12 == 8 and data[15] & 63 == 8:
        return True
    offset = 16 + (512 if data[6] & 4 else 0)
    if zlib.crc32(data[offset:]) in ZAPPER_PAYLOAD_CRCS:
        return True
    name = _title(filename)
    return any(name == _title(title) for title in ZAPPER_TITLES)
