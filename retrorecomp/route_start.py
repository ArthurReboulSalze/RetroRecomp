"""How a route reaches play: the start chosen among variants played on the reference, and the stretches where a walk left
the game still. Shared by the machines that find their start this way (the PC Engine, the MSX): STANDARDS rule 1, no
third copy. Lifted from pce_conversion.py on 12 November 2026 with the PC Engine's decisions unchanged (its tests pin them).

Everything here reads numbers about runs, never a ROM: a picture per frame (any hashable value), the frames at which a
button was pressed, and the liveness records of delivery_evidence. Each machine reads its own traces and gives them here
as plain tables; the thresholds that are a machine's choice (the walk's quiet length, the pair gap, what "still" means)
are its arguments.
"""
from __future__ import annotations

from typing import Callable, Hashable, Mapping, Sequence


def liveness_score(liveness: Mapping) -> tuple:
    """How alive a route stayed: the latest picture change first, then the number of changes, then audible frames."""
    return (liveness.get('last_picture_change_frame') or 0, liveness.get('picture_changes') or 0,
            liveness.get('audible_frames') or 0)


def divergence(pictures: Mapping[Hashable, Hashable], baseline: Mapping[Hashable, Hashable]) -> int:
    """Frames whose picture differs from the same frame of the route without input (both maps: frame -> picture): what the
    input changed on screen. A variant whose presses the game ignored (it kept playing its demo) has none."""
    return sum(1 for frame, value in pictures.items() if baseline.get(frame) != value)


def reach(pictures: Mapping[int, Hashable], baseline: Mapping[int, Hashable], start: int, window: int) -> int:
    """How many distinct pictures the frames `start` to `start + window` (the directions-only part of a walk) showed that the
    same frames without input never showed: how much the game answers the pad. A demo, a title, a story and a paused game
    show the same pictures with or without the walk, a menu a handful, a game in play hundreds of its own."""
    def seen(table):
        return {value for frame, value in table.items() if start <= frame < start + window}
    return len(seen(pictures) - seen(baseline))


def stuck_stretch(pictures: Sequence[Hashable], pressed: Sequence[int], *, pair_gap: int, stuck_frames: int,
                  stuck_share: float, press_frames: int = 6, after: int = 0) -> tuple[int, int] | None:
    """The first stretch from the end of a pair of presses (or of an extra press) to the next press or to the end of the route,
    starting at or after `after`, in which the picture hardly changes (at most `stuck_share` of its frames distinct, over at
    least `stuck_frames`): a pause the walk left on, a prompt or a screen that waits. `pressed` are the frames at which the
    start button went down, a pair being two presses `pair_gap` frames apart; a press lasts `press_frames`. None when none."""
    pairs = [frame for frame in pressed if frame + pair_gap in pressed]
    if not pairs:
        return None
    seconds = {frame + pair_gap for frame in pairs}
    ends = sorted({frame + press_frames for frame in pressed if frame in seconds or (frame > pairs[0] and frame not in pairs)})
    for start in ends:
        if start < after:
            continue
        end = next((frame for frame in pressed if frame > start), len(pictures))
        length = end - start
        if length >= stuck_frames and len(set(pictures[start:end])) <= stuck_share * length:
            return start, end
    return None


def choose_start(results: Mapping, frames: int, order: Callable[[Hashable], tuple]) -> Hashable:
    """The start variant of the play route. `results` maps variants to {'liveness', 'divergence', 'reach'}; `order(variant)`
    is the machine's tie-break (fewest presses first).

    A variant must keep the picture moving until its last 120 frames (a press too many pauses the game); among those, the
    one whose walk reached the most pictures of its own wins, then the one the input changed the most from the demo, then
    `order`. When none stays alive, the livelier one is kept."""
    alive = [variant for variant, result in results.items()
             if (result['liveness'].get('last_picture_change_frame') or 0) >= frames - 120]
    if alive:
        return min(alive, key=lambda variant: (-results[variant]['reach'], -results[variant]['divergence'], *order(variant)))
    return min(results, key=lambda variant: (-liveness_score(results[variant]['liveness'])[0],
                                             -liveness_score(results[variant]['liveness'])[1],
                                             -liveness_score(results[variant]['liveness'])[2], *order(variant)))
