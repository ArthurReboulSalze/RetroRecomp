"""Authored gameplay routes for exact Super FX cartridges (host inputs only).

The random extended route never leaves the menus of some Super FX games, so a
conversion at the Extended level and above also replays the authored routes of
the exact ROM (SHA-256) when this table holds it: one route named ``authored``
for most games, more than one where a game has a mode the first route does not
play (Stunt Race FX adds ``authored-2p``, its two-controller Battle Trax; each
route is its own scenario, with its own script hash). A route is a list of controller
states for the headless host (``--input-script``, ``frame p1 p2`` decimal SNES
masks, see ``random_routes.SNES_BITS``): no guest memory or code is patched and
no ROM byte is stored here. The same script drives the native export and its
reference run, and ``tools/snes_packed_check.py`` regenerates it from the ROM
identity of the report.

Events are ``(frame, p1, p2)`` or ``('rep', first_frame, period, count,
((offset, p1, p2), ...))``, a block repeated ``count`` times every ``period``
frames. Each entry says what the route reaches ('reaches'); the routes were
written by hand against the exports of 26 October 2026 and checked with
pictures (docs/SNES_SUPERFX.md). A route proves host inputs reach that game
state in the export; it does not prove gameplay is correct.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

LINE_LIMIT = 4096  # the 16-bit replay holds this many lines (random_routes.CONSOLE16_LINE_LIMIT)
# A scenario name is also a file name (``<name>-inputs.txt``) and a report key: it must be
# unique among the scenarios of a conversion (the probe names and the random routes' ``long-N``).
SCENARIO_NAME = re.compile('[a-z][a-z0-9]*(-[a-z0-9]+)*')
LONG_ROUTE_NAME = re.compile('long-[0-9]+')
RESERVED_SCENARIOS = frozenset({'demo', 'play', 'advanced', 'early-start', 'menu-confirm'})

ROUTES = {
    '82e39dfbb3e4fe5c28044e80878392070c618b298dd5a267e5ea53c8f72cc548': {
        'title': 'Star Fox (USA)', 'frames': 9000,
        'reaches': (
            'Start taps through title, controls and map; A taps pick Corneria and the briefing; '
            'Corneria flight from about frame 3,900 (direction cycle with B).'),
        'events': ((0, 0, 0), ('rep', 300, 200, 10, ((0, 8, 0), (4, 0, 0))),
             ('rep', 2200, 200, 8, ((0, 256, 0), (4, 0, 0))),
             ('rep', 4000, 540, 9,
              ((0, 128, 0), (6, 129, 0), (12, 128, 0), (18, 129, 0), (24, 128, 0), (30, 129, 0), (36, 128, 0),
               (42, 129, 0), (48, 128, 0), (54, 129, 0), (60, 128, 0), (66, 129, 0), (72, 128, 0), (78, 129, 0),
               (84, 128, 0), (90, 17, 0), (96, 16, 0), (102, 17, 0), (108, 16, 0), (114, 17, 0), (120, 16, 0),
               (126, 17, 0), (132, 16, 0), (138, 17, 0), (144, 16, 0), (150, 17, 0), (156, 16, 0), (162, 17, 0),
               (168, 16, 0), (174, 17, 0), (180, 64, 0), (186, 65, 0), (192, 64, 0), (198, 65, 0), (204, 64, 0),
               (210, 65, 0), (216, 64, 0), (222, 65, 0), (228, 64, 0), (234, 65, 0), (240, 64, 0), (246, 65, 0),
               (252, 64, 0), (258, 65, 0), (264, 64, 0), (270, 33, 0), (276, 32, 0), (282, 33, 0), (288, 32, 0),
               (294, 33, 0), (300, 32, 0), (306, 33, 0), (312, 32, 0), (318, 33, 0), (324, 32, 0), (330, 33, 0),
               (336, 32, 0), (342, 33, 0), (348, 32, 0), (354, 33, 0), (360, 144, 0), (366, 145, 0), (372, 144, 0),
               (378, 145, 0), (384, 144, 0), (390, 145, 0), (396, 144, 0), (402, 145, 0), (408, 144, 0),
               (414, 145, 0), (420, 144, 0), (426, 145, 0), (432, 144, 0), (438, 145, 0), (444, 144, 0),
               (450, 97, 0), (456, 96, 0), (462, 97, 0), (468, 96, 0), (474, 97, 0), (480, 96, 0), (486, 97, 0),
               (492, 96, 0), (498, 97, 0), (504, 96, 0), (510, 97, 0), (516, 96, 0), (522, 97, 0), (528, 96, 0),
               (534, 97, 0))),
             ('rep', 8860, 12, 7, ((0, 128, 0), (6, 129, 0))), (8944, 128, 0),
             ('rep', 8950, 12, 4, ((0, 17, 0), (6, 16, 0))), (8998, 17, 0))},
    'e134f20f6ee7d422d06faea6b1ae1e4101d1d0a200a0571d715d1cf23d959e8c': {
        'title': 'Star Fox 2 (USA)', 'frames': 12000,
        'reaches': (
            'Start taps to the pilot select and launch; B taps through the tutorial; the map, then '
            'a battle from about frame 7,300 (direction blocks with B).'),
        'events': ((0, 0, 0), ('rep', 240, 240, 11, ((0, 8, 0), (4, 0, 0))),
             ('rep', 3300, 90, 30, ((0, 1, 0), (4, 0, 0))),
             ('rep', 6000, 1920, 3,
              ((0, 16, 0), (30, 17, 0), (34, 16, 0), (60, 16, 0), (90, 17, 0), (94, 16, 0), (120, 16, 0),
               (150, 17, 0), (154, 16, 0), (180, 16, 0), (210, 17, 0), (214, 16, 0), (240, 128, 0), (270, 129, 0),
               (274, 128, 0), (300, 128, 0), (330, 129, 0), (334, 128, 0), (360, 128, 0), (390, 129, 0),
               (394, 128, 0), (420, 128, 0), (450, 129, 0), (454, 128, 0), (480, 32, 0), (510, 33, 0), (514, 32, 0),
               (540, 32, 0), (570, 33, 0), (574, 32, 0), (600, 32, 0), (630, 33, 0), (634, 32, 0), (660, 32, 0),
               (690, 33, 0), (694, 32, 0), (720, 64, 0), (750, 65, 0), (754, 64, 0), (780, 64, 0), (810, 65, 0),
               (814, 64, 0), (840, 64, 0), (870, 65, 0), (874, 64, 0), (900, 64, 0), (930, 65, 0), (934, 64, 0),
               (960, 144, 0), (990, 145, 0), (994, 144, 0), (1020, 144, 0), (1050, 145, 0), (1054, 144, 0),
               (1080, 144, 0), (1110, 145, 0), (1114, 144, 0), (1140, 144, 0), (1170, 145, 0), (1174, 144, 0),
               (1200, 96, 0), (1230, 97, 0), (1234, 96, 0), (1260, 96, 0), (1290, 97, 0), (1294, 96, 0),
               (1320, 96, 0), (1350, 97, 0), (1354, 96, 0), (1380, 96, 0), (1410, 97, 0), (1414, 96, 0),
               (1440, 160, 0), (1470, 161, 0), (1474, 160, 0), (1500, 160, 0), (1530, 161, 0), (1534, 160, 0),
               (1560, 160, 0), (1590, 161, 0), (1594, 160, 0), (1620, 160, 0), (1650, 161, 0), (1654, 160, 0),
               (1680, 80, 0), (1710, 81, 0), (1714, 80, 0), (1740, 80, 0), (1770, 81, 0), (1774, 80, 0),
               (1800, 80, 0), (1830, 81, 0), (1834, 80, 0), (1860, 80, 0), (1890, 81, 0), (1894, 80, 0))),
             ('rep', 11760, 60, 4, ((0, 16, 0), (30, 17, 0), (34, 16, 0))))},
    'c04d80b84514202ff319384ca20641eb0189e975eed5612915bd9c224b2ab30a': (
        {'name': 'authored', 'title': 'Stunt Race FX (USA)', 'frames': 6000,
         'reaches': (
             'Ten Start taps through the menus to Speed Trax; B held to accelerate from about frame '
             '3,000.'),
         'events': ((0, 0, 0), ('rep', 240, 240, 10, ((0, 8, 0), (4, 0, 0))), (3000, 1, 0))},
        # Two controllers: Game Selection > Battle Trax, car selection by pad 1 then pad 2,
        # Cotton Farm (split screen), both pads accelerate (B) and steer on opposite phases with
        # an A tap for the boost. Pad 1 is wrecked near frame 6,600 ("WIN" on pad 2's half), the
        # TRY AGAIN / CHANGE COURSE / CHANGE CAR menu follows; CHANGE COURSE, Toxic Desert, a second
        # split-screen race with the steering phases swapped until the end of the route.
        {'name': 'authored-2p', 'title': 'Stunt Race FX (USA), two players', 'frames': 12000,
         'reaches': (
             'Start taps to Game Selection; Down twice and Start pick Battle Trax; pad 1 then pad 2 pick '
             'a car; Cotton Farm split-screen race from about frame 1,800 (both pads drive, pad 1 wrecked '
             'near 6,600); CHANGE COURSE, Right and Start pick Toxic Desert for a second split-screen '
             'race from about frame 8,100.'),
         'events': ((0, 0, 0), (240, 8, 0), (244, 0, 0), (360, 8, 0), (364, 0, 0), (600, 8, 0), (604, 0, 0),
                    (840, 32, 0), (844, 0, 0), (860, 32, 0), (864, 0, 0), (900, 8, 0), (904, 0, 0),
                    (1020, 8, 0), (1024, 0, 0), (1110, 0, 8), (1114, 0, 0), (1350, 8, 0), (1354, 0, 0),
                    (1500, 8, 0), (1504, 0, 0),
                    ('rep', 1800, 240, 22,
                     ((0, 1, 1), (20, 1, 129), (50, 1, 1), (60, 65, 1), (90, 1, 1), (110, 1, 65), (140, 1, 1),
                      (150, 129, 1), (180, 1, 1), (200, 1, 257), (210, 1, 1))),
                    (7080, 0, 0), (7320, 32, 0), (7324, 0, 0), (7350, 8, 0), (7354, 0, 0),
                    (7600, 128, 0), (7604, 0, 0), (7650, 8, 0), (7654, 0, 0), (7890, 8, 0), (7894, 0, 0),
                    ('rep', 8130, 240, 16,
                     ((0, 1, 1), (20, 129, 1), (50, 1, 1), (60, 1, 65), (90, 1, 1), (110, 65, 1), (140, 1, 1),
                      (150, 1, 129), (180, 1, 1), (200, 257, 1), (210, 1, 1))))}),
    'bd763c1a56365c244be92e6cffefd318780a2a19eda7d5baf1c6d5bd6c1b3e06': {
        'title': "Super Mario World 2 - Yoshi's Island (USA)", 'frames': 9000,
        'reaches': (
            'Start, then A taps through the file select and intro; level 1-1 from about frame 4,000 '
            '(Right with A, Y and X).'),
        'events': ((0, 0, 0), (300, 8, 0), (304, 0, 0), ('rep', 700, 40, 83, ((0, 256, 0), (4, 0, 0))), (4000, 386, 0),
             (4025, 640, 0), (4050, 128, 0), (4075, 128, 0), (4100, 128, 0), (4125, 128, 0), (4150, 384, 0),
             (4175, 128, 0), (4200, 128, 0), (4225, 128, 0), (4250, 128, 0), (4275, 640, 0), (4300, 384, 0),
             (4325, 128, 0), (4350, 130, 0), (4375, 128, 0), (4400, 128, 0), (4425, 128, 0), (4450, 384, 0),
             (4475, 128, 0), (4500, 128, 0), (4525, 640, 0), (4550, 128, 0), (4575, 128, 0), (4600, 384, 0),
             (4625, 128, 0), (4650, 128, 0), (4675, 128, 0), (4700, 130, 0), (4725, 128, 0), (4750, 384, 0),
             (4775, 640, 0), (4800, 128, 0), (4825, 128, 0), (4850, 128, 0), (4875, 128, 0), (4900, 384, 0),
             (4925, 128, 0), (4950, 128, 0), (4975, 128, 0), (5000, 128, 0), (5025, 640, 0), (5050, 386, 0),
             ('rep', 5075, 25, 5, ((0, 128, 0),)), (5200, 384, 0), (5225, 128, 0), (5250, 128, 0), (5275, 640, 0),
             (5300, 128, 0), (5325, 128, 0), (5350, 384, 0), (5375, 128, 0), (5400, 130, 0), (5425, 128, 0),
             (5450, 128, 0), (5475, 128, 0), (5500, 384, 0), (5525, 640, 0), (5550, 128, 0), (5575, 128, 0),
             (5600, 128, 0), (5625, 128, 0), (5650, 384, 0), (5675, 128, 0), (5700, 128, 0), (5725, 128, 0),
             (5750, 130, 0), (5775, 640, 0), (5800, 384, 0), ('rep', 5825, 25, 5, ((0, 128, 0),)), (5950, 384, 0),
             (5975, 128, 0), (6000, 128, 0), (6025, 640, 0), (6050, 128, 0), (6075, 128, 0), (6100, 386, 0),
             ('rep', 6125, 25, 5, ((0, 128, 0),)), (6250, 384, 0), (6275, 640, 0), (6300, 128, 0), (6325, 128, 0),
             (6350, 128, 0), (6375, 128, 0), (6400, 384, 0), (6425, 128, 0), (6450, 130, 0), (6475, 128, 0),
             (6500, 128, 0), (6525, 640, 0), (6550, 384, 0), ('rep', 6575, 25, 5, ((0, 128, 0),)), (6700, 384, 0),
             (6725, 128, 0), (6750, 128, 0), (6775, 640, 0), (6800, 130, 0), (6825, 128, 0), (6850, 384, 0),
             ('rep', 6875, 25, 5, ((0, 128, 0),)), (7000, 384, 0), (7025, 640, 0), (7050, 128, 0), (7075, 128, 0),
             (7100, 128, 0), (7125, 128, 0), (7150, 386, 0), (7175, 128, 0), (7200, 128, 0), (7225, 128, 0),
             (7250, 128, 0), (7275, 640, 0), (7300, 384, 0), ('rep', 7325, 25, 5, ((0, 128, 0),)), (7450, 384, 0),
             (7475, 128, 0), (7500, 130, 0), (7525, 640, 0), (7550, 128, 0), (7575, 128, 0), (7600, 384, 0),
             ('rep', 7625, 25, 5, ((0, 128, 0),)), (7750, 384, 0), (7775, 640, 0), (7800, 128, 0), (7825, 128, 0),
             (7850, 130, 0), (7875, 128, 0), (7900, 384, 0), (7925, 128, 0), (7950, 128, 0), (7975, 128, 0),
             (8000, 128, 0), (8025, 640, 0), (8050, 384, 0), ('rep', 8075, 25, 5, ((0, 128, 0),)), (8200, 386, 0),
             (8225, 128, 0), (8250, 128, 0), (8275, 640, 0), (8300, 128, 0), (8325, 128, 0), (8350, 384, 0),
             ('rep', 8375, 25, 5, ((0, 128, 0),)), (8500, 384, 0), (8525, 640, 0), (8550, 130, 0), (8575, 128, 0),
             (8600, 128, 0), (8625, 128, 0), (8650, 384, 0), (8675, 128, 0), (8700, 128, 0), (8725, 128, 0),
             (8750, 128, 0), (8775, 640, 0), (8800, 384, 0), (8825, 128, 0), (8850, 128, 0), (8875, 128, 0),
             (8900, 130, 0), (8925, 128, 0), (8950, 384, 0), (8975, 128, 0))},
    '41b5561de9e4984276e52987ea46c5f4fa8526d8141c70c738875a9eb9fe9d70': {
        'title': 'Vortex (USA)', 'frames': 8000,
        'reaches': (
            'Start taps through the menus; the first mission from about frame 2,800 (directions '
            'with B and A).'),
        'events': ((0, 0, 0), ('rep', 240, 240, 10, ((0, 8, 0), (4, 0, 0))), (3000, 385, 0), (3030, 128, 0),
             (3060, 129, 0), (3090, 128, 0), (3120, 129, 0), (3150, 128, 0), (3180, 65, 0), (3210, 64, 0),
             (3240, 65, 0), (3270, 272, 0), (3300, 17, 0), (3330, 16, 0), (3360, 33, 0), (3390, 32, 0),
             (3420, 33, 0), (3450, 128, 0), (3480, 129, 0), (3510, 128, 0), (3540, 321, 0), (3570, 64, 0),
             (3600, 65, 0), (3630, 0, 0), (3660, 1, 0), (3690, 0, 0), (3720, 129, 0), (3750, 128, 0),
             (3780, 129, 0), (3810, 384, 0), (3840, 129, 0), (3870, 128, 0), (3900, 65, 0), (3930, 64, 0),
             (3960, 65, 0), (3990, 16, 0), (4020, 17, 0), (4050, 16, 0), (4080, 289, 0), (4110, 32, 0),
             (4140, 33, 0), (4170, 128, 0), (4200, 129, 0), (4230, 128, 0), (4260, 65, 0), (4290, 64, 0),
             (4320, 65, 0), (4350, 256, 0), (4380, 1, 0), (4410, 0, 0), (4440, 129, 0), (4470, 128, 0),
             (4500, 129, 0), (4530, 128, 0), (4560, 129, 0), (4590, 128, 0), (4620, 321, 0), (4650, 64, 0),
             (4680, 65, 0), (4710, 16, 0), (4740, 17, 0), (4770, 16, 0), (4800, 33, 0), (4830, 32, 0),
             (4860, 33, 0), (4890, 384, 0), (4920, 129, 0), (4950, 128, 0), (4980, 65, 0), (5010, 64, 0),
             (5040, 65, 0), (5070, 0, 0), (5100, 1, 0), (5130, 0, 0), (5160, 385, 0), (5190, 128, 0),
             (5220, 129, 0), (5250, 128, 0), (5280, 129, 0), (5310, 128, 0), (5340, 65, 0), (5370, 64, 0),
             (5400, 65, 0), (5430, 272, 0), (5460, 17, 0), (5490, 16, 0), (5520, 33, 0), (5550, 32, 0),
             (5580, 33, 0), (5610, 128, 0), (5640, 129, 0), (5670, 128, 0), (5700, 321, 0), (5730, 64, 0),
             (5760, 65, 0), (5790, 0, 0), (5820, 1, 0), (5850, 0, 0), (5880, 129, 0), (5910, 128, 0),
             (5940, 129, 0), (5970, 384, 0), (6000, 129, 0), (6030, 128, 0), (6060, 65, 0), (6090, 64, 0),
             (6120, 65, 0), (6150, 16, 0), (6180, 17, 0), (6210, 16, 0), (6240, 289, 0), (6270, 32, 0),
             (6300, 33, 0), (6330, 128, 0), (6360, 129, 0), (6390, 128, 0), (6420, 65, 0), (6450, 64, 0),
             (6480, 65, 0), (6510, 256, 0), (6540, 1, 0), (6570, 0, 0), (6600, 129, 0), (6630, 128, 0),
             (6660, 129, 0), (6690, 128, 0), (6720, 129, 0), (6750, 128, 0), (6780, 321, 0), (6810, 64, 0),
             (6840, 65, 0), (6870, 16, 0), (6900, 17, 0), (6930, 16, 0), (6960, 33, 0), (6990, 32, 0),
             (7020, 33, 0), (7050, 384, 0), (7080, 129, 0), (7110, 128, 0), (7140, 65, 0), (7170, 64, 0),
             (7200, 65, 0), (7230, 0, 0), (7260, 1, 0), (7290, 0, 0), (7320, 385, 0), (7350, 128, 0),
             (7380, 129, 0), (7410, 128, 0), (7440, 129, 0), (7470, 128, 0), (7500, 65, 0), (7530, 64, 0),
             (7560, 65, 0), (7590, 272, 0), (7620, 17, 0), (7650, 16, 0), (7680, 33, 0), (7710, 32, 0),
             (7740, 33, 0), (7770, 128, 0), (7800, 129, 0), (7830, 128, 0), (7860, 321, 0), (7890, 64, 0),
             (7920, 65, 0), (7950, 0, 0), (7980, 1, 0))},
    '3994e7dc9f86d2dd06bc0bb431567d3e7c83eff1d89e2f10bb0cc5a400e762b0': {
        'title': 'Dirt Racer (Europe)', 'frames': 7000,
        'reaches': (
            'Start taps, Down and Start into Cup, then Start and A alternating; the first race from '
            'about frame 2,400.'),
        'events': ((0, 0, 0), ('rep', 240, 240, 4, ((0, 8, 0), (4, 0, 0))), (1300, 32, 0), (1304, 0, 0), (1400, 8, 0),
             (1408, 0, 0), ('rep', 1600, 240, 22, ((0, 8, 0), (6, 0, 0), (120, 256, 0), (126, 0, 0))), (6880, 8, 0),
             (6886, 0, 0))},
}


def expand(events) -> tuple:
    """The flat ``(frame, p1, p2)`` list of a route, validated."""
    flat = []
    for item in events:
        if item and item[0] == 'rep':
            _, first, period, count, body = item
            flat.extend((first + step * period + offset, p1, p2)
                        for step in range(count) for offset, p1, p2 in body)
        else:
            flat.append(tuple(item))
    previous = -1
    for frame, p1, p2 in flat:
        if (not all(type(value) is int for value in (frame, p1, p2)) or frame <= previous
                or not 0 <= p1 <= 0xffff or not 0 <= p2 <= 0xffff):
            raise ValueError('Invalid authored route event.')
        previous = frame
    if not flat or len(flat) > LINE_LIMIT:
        raise ValueError('Invalid authored route length.')
    return tuple(flat)


@dataclass(frozen=True)
class AuthoredRoute:
    """The same interface as ``random_routes.Route`` for the scenarios and reports."""
    sha256: str
    title: str
    frames: int
    events: tuple
    reaches: str
    name: str = 'authored'
    console: str = 'snes'
    continues_from: None = None

    def script(self) -> str:
        return ''.join(f'{frame} {p1} {p2}\n' for frame, p1, p2 in self.events)

    def script_sha256(self) -> str:
        return hashlib.sha256(self.script().encode('ascii')).hexdigest()

    def metadata(self) -> dict:
        return {'scenario': self.name, 'kind': 'authored', 'frames': self.frames,
                'steps': len(self.events), 'rom_sha256': self.sha256, 'title': self.title,
                'reaches': self.reaches, 'script_sha256': self.script_sha256(),
                'continues_from': None, 'generator': 'snes_routes.authored_routes'}


def route_entries(sha256: str) -> tuple:
    """The route entries of an exact ROM: a table value is one entry (route
    ``authored``) or a tuple of entries, each naming its own scenario."""
    value = ROUTES.get(sha256)
    if value is None:
        return ()
    return (value,) if isinstance(value, dict) else tuple(value)


def authored_routes(sha256: str) -> tuple:
    """The authored routes of this exact ROM, in table order (each its own
    scenario, names unique), or an empty tuple."""
    routes, names = [], set()
    entries = route_entries(sha256)
    for entry in entries:
        name = entry.get('name', 'authored' if len(entries) == 1 else None)
        if (not isinstance(name, str) or SCENARIO_NAME.fullmatch(name) is None
                or name in RESERVED_SCENARIOS or LONG_ROUTE_NAME.fullmatch(name)):
            raise ValueError(f'Invalid authored route scenario name: {name!r}.')
        if name in names:
            raise ValueError(f'Duplicate authored route scenario name: {name}.')
        names.add(name)
        events = expand(entry['events'])
        if events[-1][0] >= entry['frames']:
            raise ValueError('An authored route must end before its last frame.')
        routes.append(AuthoredRoute(sha256, entry['title'], entry['frames'], events, entry['reaches'], name))
    return tuple(routes)
