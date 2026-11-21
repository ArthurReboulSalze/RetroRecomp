"""Exploration routes of a PC Engine CD (Retro-Recomp's own code, MIT): how a conversion reaches past a disc's menus and loading screens.

The PC Engine's routes (`pce_conversion.play_rows`) press Run a few times and then walk: directions, taps of I and II, now and then two presses of Run. That is
enough for a HuCard that starts on Run, and it stays in a menu on a disc (Ys Book I & II rests on its « Location / Start game story » menu for the whole route). A disc
is a game made of menus, cut-scenes, loading screens and levels, and each of them is answered by other inputs. The conversion therefore plays a few **styles** of
input from the same start and keeps the one that makes the game run the most different code:

* `walk`: the PC Engine's own walk, the default of every route;
* `menu`: a cursor stepped down and answered, over and over (Down, I, a pause, II to leave a screen that opened), with Run twice now and then: it walks a list of
  menu items one after the other, which a random walk does not;
* `action`: directions held and changing, I held in bursts (a shot, a sword) and II tapped (a jump), Run twice now and then.

The score of a style is the number of distinct code identities its capture holds (the engine's code capture: an address, the eight bank registers and the bytes), then the
distinct pictures: a style that reaches a level loads a level's code. Nothing here knows a game: the same three styles are played on every disc, and the report names the
scores. What a style reaches is a measure of the route (gate G9), never a claim about the game.
"""
from __future__ import annotations

from . import pce_conversion as hu

STYLES = ('walk', 'menu', 'action')
EXPLORE_FRAMES = 6000             # frames each style is played on the observing build, to be scored
MENU_STEP = 90                    # frames between two steps of the menu style
ACTION_SPAN = 60                  # frames a direction is held in the action style


def _start(presses: int, confirm: bool) -> list:
    rows = []
    for index in range(presses):
        at = hu.PRESS_SPACING * (index + 1)
        rows += [(at, hu.RUN, 0), (at + 6, 0, 0)]
        if confirm:
            rows += [(at + hu.CONFIRM_DELAY, hu.I, 0), (at + hu.CONFIRM_DELAY + 6, 0, 0)]
    return rows


def menu_rows(frames: int, seed: int, presses: int = 3, confirm: bool = False) -> list:
    """The start, then steps of MENU_STEP frames: Down, then I thirty frames later, then II on every fourth step (back out of a screen the step opened), and two presses of Run
    every RUN_PAIR_EVERY frames. A step is one list item: the items of a menu are answered one after the other."""
    rows = _start(presses, confirm)
    frame = hu.walk_start(presses)
    pair = frame + hu.RUN_PAIR_EVERY
    step = 0
    state = seed & 0xFFFFFFFF or 1
    while frame + MENU_STEP < frames:
        if frame >= pair:
            rows += [(frame, hu.RUN, 0), (frame + 6, 0, 0), (frame + hu.PAIR_GAP, hu.RUN, 0), (frame + hu.PAIR_GAP + 6, 0, 0)]
            frame += 40
            pair = frame + hu.RUN_PAIR_EVERY
            continue
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        rows += [(frame, hu.DOWN, 0), (frame + 6, 0, 0), (frame + 30, hu.I, 0), (frame + 36, 0, 0)]
        if step % 4 == 3:
            rows += [(frame + 60, hu.II, 0), (frame + 66, 0, 0)]
        if state % 9 == 0:                      # an occasional step up or to the side: a list that wraps, a menu of columns
            rows += [(frame + 72, hu.UP if state & 0x100 else hu.RIGHT, 0), (frame + 76, 0, 0)]
        frame += MENU_STEP
        step += 1
    return [row for row in sorted(rows, key=lambda r: r[0]) if row[0] < frames]


def action_rows(frames: int, seed: int, presses: int = 3, confirm: bool = False) -> list:
    """The start, then directions held for ACTION_SPAN frames and changing, I held for the first half of each span in bursts of taps (a shot or a sword is a press, not a
    hold), II tapped in the middle (a jump), and two presses of Run every RUN_PAIR_EVERY frames (a pause and its end, a continue prompt)."""
    rows = _start(presses, confirm)
    frame = hu.walk_start(presses)
    pair = frame + hu.RUN_PAIR_EVERY
    state = seed & 0xFFFFFFFF or 1
    directions = (hu.RIGHT, hu.RIGHT | hu.UP, hu.RIGHT | hu.DOWN, hu.LEFT, hu.UP, hu.DOWN, hu.RIGHT, hu.RIGHT)
    while frame + ACTION_SPAN < frames:
        if frame >= pair:
            rows += [(frame, hu.RUN, 0), (frame + 6, 0, 0), (frame + hu.PAIR_GAP, hu.RUN, 0), (frame + hu.PAIR_GAP + 6, 0, 0)]
            frame += 40
            pair = frame + hu.RUN_PAIR_EVERY
            continue
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        held = directions[state % len(directions)]
        rows.append((frame, held, 0))
        for tap in range(0, ACTION_SPAN // 2, 10):
            rows += [(frame + tap + 2, held | hu.I, 0), (frame + tap + 6, held, 0)]
        rows += [(frame + ACTION_SPAN // 2 + 4, held | hu.II, 0), (frame + ACTION_SPAN // 2 + 10, held, 0)]
        frame += ACTION_SPAN
    rows = sorted(rows, key=lambda r: r[0])
    return [row for row in rows if row[0] < frames]


def rows(style: str, frames: int, seed: int, presses: int = 3, confirm: bool = False) -> list:
    if style == 'menu':
        return menu_rows(frames, seed, presses, confirm)
    if style == 'action':
        return action_rows(frames, seed, presses, confirm)
    if style == 'walk':
        return hu.play_rows(frames, seed, presses, (), confirm)
    raise ValueError(f'unknown route style: {style}')


def script(style: str, frames: int, seed: int, presses: int = 3, confirm: bool = False) -> str:
    return hu._script(rows(style, frames, seed, presses, confirm))


def score(result: dict, liveness: dict) -> tuple:
    """What a style reached: the distinct code identities its capture holds, then its distinct pictures."""
    return (int(result.get('capture_identities') or 0), int(liveness.get('distinct_pictures') or 0))


def explore(candidate, folder, identity: str, presses: int, confirm: bool, extra: tuple, emit) -> list[dict]:
    """Play every style for EXPLORE_FRAMES on the observing build with the engine's code capture, and return them best first:
    [{'style', 'identities', 'pictures', 'last_picture_change_frame'}]. The runs are the conversion's own (nothing is kept but their scores)."""
    from pathlib import Path
    out = []
    for style in STYLES:
        name = f'explore-{style}'
        path = Path(folder) / 'inputs' / (name + '.inputs')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(script(style, EXPLORE_FRAMES, hu.route_seed(identity, 'play'), presses, confirm), encoding='ascii', newline='\n')
        capture = Path(folder) / 'explore' / (name + '-capture.jsonl')
        capture.parent.mkdir(parents=True, exist_ok=True)
        result = hu.run(candidate, capture.parent, name, EXPLORE_FRAMES, path, '--code-capture', str(capture), '--capture-limit', str(hu.EXTENDED_CAPTURE_LIMIT), *extra)
        liveness = hu.route_liveness(Path(result['trace']))
        identities, pictures = score(result, liveness)
        out.append({'style': style, 'identities': identities, 'pictures': pictures, 'last_picture_change_frame': liveness.get('last_picture_change_frame')})
        emit(f'PC Engine CD: route style {style}: {identities} code identities, {pictures} distinct pictures in {EXPLORE_FRAMES} frames.')
    return sorted(out, key=lambda row: (row['identities'], row['pictures']), reverse=True)
