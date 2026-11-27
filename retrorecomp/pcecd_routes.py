"""Exploration routes of a PC Engine CD (Retro-Recomp's own code, MIT): how a conversion reaches past a disc's menus and loading screens.

The PC Engine's routes (`pce_conversion.play_rows`) press Run a few times and then walk: directions, taps of I and II, now and then two presses of Run. That is
enough for a HuCard that starts on Run, and it stays in a menu on a disc. A disc is a game made of menus, file screens, cut-scenes, loading screens and levels, and
each of them is answered by other inputs. The long route of a conversion is therefore built **segment by segment**: from the state at the end of what was chosen so far,
each **style** of input plays the next segment, and the style that makes the game run the most code **not run before** is kept. The styles:

* `walk`: the PC Engine's own walk, the default of every route;
* `menu`: a cursor stepped down and answered, over and over (Down, I, a pause, II to leave a screen that opened), with Run twice now and then: it walks a list of
  menu items one after the other, which a random walk does not;
* `action`: directions held and changing, I held in bursts (a shot, a sword) and II tapped (a jump), Run twice now and then;
* `tap`: single taps of any button, one after the other: it types on a name entry grid and confirms it, which the three others do not.

Code not run before is counted as the engine's code capture identities (an address, the eight bank registers and the bytes); then the distinct pictures. Nothing here
knows a game: the same styles are tried on every disc, and the report names each segment's choice and scores. What the route reaches is a measure of the route (gate G9),
never a claim about the game. The segments continue from quick states, whose continuation of a timeline is checked by every conversion; the long route the conversion
then plays, compares and ships is the composed script, played from the start.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from . import pce_conversion as hu

STYLES = ('walk', 'menu', 'action', 'tap')
SEGMENT_FRAMES = 3600             # frames of one exploration segment: one minute of the game
LONG_FRAMES = 6 * SEGMENT_FRAMES  # the explored long route: a disc's title, file screens, menus and opening scenes take minutes before play (Dracula X: past 18,000 frames)
MENU_STEP = 90                    # frames between two steps of the menu style
ACTION_SPAN = 60                  # frames a direction is held in the action style
TAP_BUTTONS = (hu.RUN, hu.I, hu.I, hu.I, hu.II, hu.UP, hu.DOWN, hu.LEFT, hu.RIGHT, hu.RUN)   # the tap style's draw: I three times, Run twice
TAP_SPACING = (18, 30)            # frames from one tap to the next: a base and a seeded extra
WORKERS = 2                       # the styles of a segment are played two at a time


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


def tap_rows(frames: int, seed: int, presses: int = 3, confirm: bool = False) -> list:
    """The start, then one tap after another, the button drawn by the seed (TAP_BUTTONS), TAP_SPACING apart."""
    rows = _start(presses, confirm)
    frame = hu.walk_start(presses)
    state = seed & 0xFFFFFFFF or 1
    while frame + 40 < frames:
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        rows += [(frame, TAP_BUTTONS[(state >> 8) % len(TAP_BUTTONS)], 0), (frame + 6, 0, 0)]
        frame += TAP_SPACING[0] + (state >> 3) % TAP_SPACING[1]
    return [row for row in rows if row[0] < frames]


def rows(style: str, frames: int, seed: int, presses: int = 3, confirm: bool = False) -> list:
    if style == 'menu':
        return menu_rows(frames, seed, presses, confirm)
    if style == 'action':
        return action_rows(frames, seed, presses, confirm)
    if style == 'tap':
        return tap_rows(frames, seed, presses, confirm)
    if style == 'walk':
        return hu.play_rows(frames, seed, presses, (), confirm)
    raise ValueError(f'unknown route style: {style}')


def script(style: str, frames: int, seed: int, presses: int = 3, confirm: bool = False) -> str:
    return hu._script(rows(style, frames, seed, presses, confirm))


def segment_rows(style: str, begin: int, end: int, seed: int, presses: int = 3, confirm: bool = False) -> list:
    """The rows of `style` for the frames [begin, end): the first segment is the style with the start; a later one releases the pads at `begin` and then plays the style's
    rows of that span (made without a start, so that a segment is only the style's own inputs)."""
    if not begin:
        return rows(style, end, seed, presses, confirm)
    return [(begin, 0, 0)] + [row for row in rows(style, end, seed, 0, False) if begin < row[0] < end]


def identities(capture: Path) -> set:
    """The code identities of an engine capture of format 2 (one observation per line)."""
    out = set()
    with open(capture, encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('{"pc"'):
                row = json.loads(line)
                out.add((row['pc'], tuple(row['mpr']), tuple(row['data'])))
    return out


def segment_seed(identity: str, index: int) -> int:
    return hu.route_seed(identity, 'play') + 7919 * index


def chain(candidate, folder: Path, identity: str, frames: int, presses: int, confirm: bool, extra: tuple, emit,
          segment: int = SEGMENT_FRAMES, workers: int = WORKERS) -> tuple[str, list[dict]]:
    """(script of `frames`, the segments' choices) of the long route, built on the observing build as said in the module's head. `extra`: the disc arguments.
    Every run is the conversion's own, in `folder`/explore; nothing is kept but the script and the scores."""
    folder = Path(folder) / 'explore'
    seen: set = set()
    chosen: list = []
    state = None
    report = []
    for index in range((frames + segment - 1) // segment):
        begin, end = index * segment, min(frames, (index + 1) * segment)
        seed = segment_seed(identity, index)

        def play(style, begin=begin, end=end, seed=seed, state=state, chosen=tuple(chosen), index=index):
            name = f's{index}-{style}'
            work = folder / name
            work.mkdir(parents=True, exist_ok=True)
            candidate_rows = list(chosen) + segment_rows(style, begin, end, seed, presses, confirm)
            path = work / 'route.inputs'
            path.write_text(hu._script(candidate_rows), encoding='ascii', newline='\n')
            saved, capture = work / 'end.rrstate', work / 'capture.jsonl'
            options = ['--code-capture', str(capture), '--capture-limit', str(hu.EXTENDED_CAPTURE_LIMIT), '--save-state', str(saved), '--save-at', str(end)]
            if state:
                options += ['--load-state', str(state)]
            count = end - begin + 1
            result = hu.run(candidate, work, name, count, path, *options, *extra, ends_at=end + 1 if state else None)
            return {'style': style, 'identities': identities(capture), 'pictures': hu.route_liveness(Path(result['trace'])).get('distinct_pictures', 0),
                    'rows': candidate_rows, 'state': saved, 'capture': capture}

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            trials = list(pool.map(play, STYLES))
        scored = [(len(t['identities'] - seen), t['pictures'], -n) for n, t in enumerate(trials)]       # a tie keeps the earlier style
        best = trials[max(range(len(trials)), key=lambda n: scored[n])]
        report.append({'from': begin, 'to': end, 'style': best['style'], 'new_identities': len(best['identities'] - seen),
                       'scores': {t['style']: [len(t['identities'] - seen), t['pictures']] for t in trials}})
        seen |= best['identities']
        chosen, state = best['rows'], best['state']
        emit(f'PC Engine CD: exploration {begin}-{end}: {best["style"]}, {report[-1]["new_identities"]} new code identities ({len(seen)} so far).')
        for trial in trials:        # the captures are large and the states of the other styles are not needed
            trial['capture'].unlink(missing_ok=True)
            if trial is not best:
                trial['state'].unlink(missing_ok=True)
    return hu._script(chosen), report
