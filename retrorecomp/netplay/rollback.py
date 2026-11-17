"""The rollback tier of the driver: a small fixed delay, and frames run on a prediction that is corrected afterwards.

`RollbackDriver` is the delay-lockstep driver (`lockstep.LockstepDriver`) with another way of giving frames to its game.
Everything else is the parent's, untouched: the start (HELLO, SETUP, boot digests, the host's word), the packets and their
bounds, the pause and resume protocol, time sync, the comparison of digests and **what a desync does** (`_desync`, the one
place), the ends of a match. A driver is on this tier only when `Settings.rollback` (the prediction cap k) is not 0 **and**
its game's HELLO reports a snapshot (`CAP_SNAPSHOT`, a bound, not a driven guest); any other game is driven by the parent's
`_step`, exactly as before. `driver_for` gives the plain `LockstepDriver` when rollback is not asked at all.

The algorithm (the study's section 2; `research/netcode-network-security.md` 1.3, 1.4 and 4.1):

* **Delay d**, small and fixed for the match: the host's `Settings.delay` when given (1 on a local network), else chosen
  from the measured worst path: 1 when one way plus jitter fits in half a frame, 2 otherwise (`_delay_for`). A seat's
  controls of frame F are its record of frame F + d, as on the delay tier; a seat's own record is never predicted.
* **One batch per live frame.** When the game asks for frame N (its LOCAL of N came), the driver looks at what it holds.
  The *confirmed* frames are those every seat's record is known for (C is the first that is not). A record that is missing
  is **predicted**: that seat's last known word, repeated, with no system bit (a pause or a pass of the turn is never
  guessed). The seat mapper (`seat_map.step`) turns the records of a frame, known or predicted, into port words, from the
  mapper state of the last confirmed frame: so it applies to confirmed and predicted records alike, and a token or a mode
  only ever moves on real records.
* **Correction.** The driver remembers the words its game ran for every frame not yet verified. Before the live frame it
  maps those frames again with what it knows now; the first frame R whose words differ is where the game went wrong:
  `LOAD R; RUN R silent; SAVE R+1; RUN R+1 silent; ...; SAVE N; RUN N live`, one write on the pipe. No state crosses the
  pipe. A frame is *verified* once it is confirmed and the game ran it with the confirmed words; its words then join the
  history and its mapper state becomes the base of the next mapping.
* **Prediction cap k.** Frame N runs only while N - C < k: at most k frames are ever run on a guess, so a correction
  re-runs at most k frames and the ring (k + 2 snapshots, asked in SETUP) always holds the snapshot it needs. At the cap
  the game waits, as on the delay tier: "Waiting for <name>" after a moment, the seat dropped after `drop_after`.
* **Pause** acts on confirmed frames only: when the frame whose record carries a seat's pause request is confirmed (it may
  already have been run on a prediction), the driver pauses its game before the next live frame. The seats may stop a few
  frames apart; the games compute the same frames, and resume as on the delay tier (by the frame of the request).
* **Digests** (every `digest_every` frames, and the boot digest) are of verified frames only. When the digest's frame is
  the one just before the live frame the game is asked at once; otherwise the batch goes back to the snapshot taken after
  it, asks, and returns to the present (`SAVE N; LOAD F+1; DIGEST; LOAD N`), with no frame run again. The parent compares.
* **The room's tier** (`choose_tier`): in a LAN room the host decides the tier and the LAUNCH carries it as one byte (0 the delay
  tier, 1 to 8 the rollback tier with that prediction cap). Automatic: rollback when the games' HELLOs report a snapshot, else
  the delay tier; `delay` and `rollback` are the host's overrides (`_netplay-room host --tier`). A guest whose own game reports
  no snapshot while the launch says rollback refuses the match with a reason (`Settings.rollback_required`, `_tier_refusal`).
* **The end** (`last_frame`, tests): the last frames are corrected and the last digest asked once every record is known.

Counts only (`stats`: rollbacks, frames run again, the deepest correction, frames run on a prediction, waits at the cap;
`rollback_depths[n]`: corrections of n frames). Nothing here measures a duration.
"""
from __future__ import annotations

import collections

from . import input_records as wire
from . import seat_map
from . import session_pipe as pipe
from . import control
from .launch import Refusal
from .lockstep import LINGER, MAX_PREDICTION, LockstepDriver, Settings
from .session_game import SessionGame
from .session_transport import SeatLink

# The cap k: at most 5 frames run on a guess. Measured on a quiet PC (17 Nov 2026, .build/multiplayer/bench/K_MEASURE_20261117.txt):
# a frame run again silently costs a NES export what a live frame costs (2.5 ms median), so a correction of k frames plus the
# live one must fit in one frame: 5 x 2.5 + 2.5 = 15 ms of 16.6; 8 took 20 ms and showed as a late frame.
DEFAULT_PREDICTION = 5
DELAY_LAN, DELAY_ELSE = 1, 2
RING_MARGIN = 2              # snapshots kept beyond the cap: the live frame's, and one to spare


def rollback_delay(one_way_ms: float, jitter_ms: float, frame_ms: float, cap: int = DEFAULT_PREDICTION) -> int:
    """The small fixed delay d: 1 when the worst path (one way plus jitter) fits in half a frame, as on a local network,
    2 otherwise. What it does not cover is predicted and corrected, up to the cap; a link that would need deeper guesses
    gets a larger d instead, so the expected depth (the delay that would cover the link, less d) stays within the cap."""
    small = DELAY_LAN if one_way_ms + jitter_ms <= frame_ms / 2 else DELAY_ELSE
    return max(small, wire.choose_delay(one_way_ms, jitter_ms, frame_ms) - max(1, cap))


def can_roll_back(hello: pipe.Hello) -> bool:
    """Whether this game keeps snapshots the driver may command (a driven guest runs its own frames: never silent)."""
    return bool(hello.caps & pipe.CAP_SNAPSHOT) and hello.snap_bound > 0 and not hello.caps & pipe.CAP_DRIVEN


TIER_AUTO, TIER_DELAY, TIER_ROLLBACK = 'auto', 'delay', 'rollback'
TIER_MODES = (TIER_AUTO, TIER_DELAY, TIER_ROLLBACK)


def check_tier(mode, cap) -> Refusal | None:
    """The host's own tier settings (`mode`, the prediction cap), refused with a sentence when out of bounds."""
    if mode not in TIER_MODES:
        return Refusal('a tier of auto, delay or rollback')
    if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= control.MAX_ROLLBACK:
        return Refusal(f'a prediction cap of 1 to {control.MAX_ROLLBACK} frames')
    return None


def choose_tier(mode, hellos, cap: int = DEFAULT_PREDICTION) -> int | Refusal:
    """The host's decision for a launch: the tier byte of the LAUNCH (0 the delay tier, else the prediction cap, 1 to
    `control.MAX_ROLLBACK`), or the `Refusal` that says why this launch cannot be made. `hellos` is what the games of this
    launch reported (`pipe.Hello`, None for one that did not): the match is on the rollback tier only when **every** one of them
    keeps a snapshot the driver may command (`can_roll_back`). `mode`: `auto` (that rule), `delay` (never rollback) or `rollback`
    (a test or a check between two PCs: refused, with the reason, when a game cannot)."""
    bad = check_tier(mode, cap)
    if bad is not None:
        return bad
    if mode == TIER_DELAY:
        return 0
    able = bool(hellos) and all(hello is not None and can_roll_back(hello) for hello in hellos)
    if able:
        return cap
    if mode == TIER_ROLLBACK:
        return Refusal('the rollback tier needs a game that keeps snapshots, and this one does not')
    return 0


def predicted(log) -> tuple:
    """The record guessed for a seat whose record is not known yet: its last known word, no system bit."""
    return log[len(log) - 1][0], 0


class RollbackDriver(LockstepDriver):
    def __init__(self, game: SessionGame, link: SeatLink, settings: Settings):
        super().__init__(game, link, settings)
        cap = settings.rollback
        if not isinstance(cap, int) or isinstance(cap, bool) or not 0 <= cap <= MAX_PREDICTION:
            raise ValueError(f'a prediction cap of 0 to {MAX_PREDICTION} frames')
        self.cap = cap
        self.rolling = False                    # decided by the game's HELLO
        self.ring = 0
        self.rollback_depths = [0] * (cap + 1)  # [n]: corrections that ran n frames again
        self.stats.update({'rollbacks': 0, 'rollback_frames': 0, 'rollback_depth_max': 0, 'predicted_frames': 0,
                           'cap_waits': 0, 'saves': 0, 'loads': 0, 'digests_skipped': 0})
        self._ran: dict[int, tuple] = {}        # frame -> the words the game ran it with, for the frames not verified yet
        self._verified = 0                      # the frames below were run with their confirmed words
        self._verified_state = self._seat_state # the mapper before frame `_verified`
        self._pause_checked = 0                 # the confirmed frames below were looked at for a pause request
        self._digest_due: collections.deque = collections.deque()      # frames whose digest is wanted, once verified
        self._digest_asked: collections.deque = collections.deque()    # the frames of the DIGESTs sent, in order

    # ---- the parent's hooks ----

    def _tier_refusal(self, hello: pipe.Hello) -> str | None:
        if self.settings.rollback_required and not can_roll_back(hello):
            return 'this game keeps no snapshot, but the host chose the rollback tier for the match'
        return None

    def _ring_depth(self, hello: pipe.Hello) -> int:
        self.rolling = self.cap > 0 and can_roll_back(hello)
        self.ring = min(pipe.MAX_RING, self.cap + RING_MARGIN) if self.rolling else 0
        return self.ring

    def _digest_frame(self, frame: int) -> int | None:
        if not self.rolling:
            return frame
        return self._digest_asked.popleft() if self._digest_asked else None

    def _delay_for(self, one_way_ms: float, jitter_ms: float) -> int:
        if not self.rolling:
            return super()._delay_for(one_way_ms, jitter_ms)
        return rollback_delay(one_way_ms, jitter_ms, self.hello.frame_seconds * 1000.0, self.cap)

    def _preset_hold(self) -> int | None:
        """A game that does not wait for records is not aligned by them: even with a delay given the host measures its
        links first and starts once its word reached the farthest guest, so no seat begins the match ahead of the others."""
        if not self.rolling:
            return super()._preset_hold()
        if self._own_measure() is None:
            return None
        return min(wire.MAX_HOLD_MS, int(max(self._one_way_ms.values(), default=0.0)))

    def snapshot(self) -> dict:
        state = super().snapshot()
        if self.rolling:
            state.update(tier='rollback', prediction_cap=self.cap, ring=self.ring, verified=self._verified,
                         rollback_depths=list(self.rollback_depths))
        return state

    # ---- frames ----

    def _confirmed(self) -> int:
        """The first frame some seat's record is not known for."""
        return min(len(records) for records in self._records)

    def _mapped(self, upto: int) -> list:
        """((port words, restart), mapper state after) of every frame from the first not verified to `upto`, from what is
        known now: a seat's record, or its prediction (never a restart: a predicted record has no system bit)."""
        state, out = self._verified_state, []
        for frame in range(self._verified, upto + 1):
            records = [log[frame] if frame < len(log) else predicted(log) for log in self._records]
            words, state = seat_map.step(state, records, self.settings.opposites)
            if self.settings.words_filter is not None:
                words = tuple(self.settings.words_filter(frame, words))
            out.append(((words, seat_map.restart(records)), state))
        return out

    def _correct(self, position: int, mapped: list, batch: list) -> None:
        """The frames below `position` the game ran with other words than what is known now are run again, silently,
        from the first of them."""
        base = self._verified
        wrong = next((frame for frame in range(base, position) if self._ran[frame] != mapped[frame - base][0]), None)
        if wrong is None:
            return
        batch.append(pipe.load(wrong))
        for frame in range(wrong, position):
            if frame > wrong:
                batch.append(pipe.save(frame))          # the snapshot before it was of the wrong game
                self.stats['saves'] += 1
            run = mapped[frame - base][0]
            batch.append(pipe.run(frame, run[0], silent=True, reset=run[1]))
            self._ran[frame] = run
        depth = position - wrong
        self.stats['loads'] += 1
        self.stats['rollbacks'] += 1
        self.stats['rollback_frames'] += depth
        self.stats['rollback_depth_max'] = max(self.stats['rollback_depth_max'], depth)
        self.rollback_depths[min(depth, self.cap)] += 1

    def _verify(self, limit: int, mapped: list, base: int) -> None:
        """The frames below `limit` are confirmed and the game ran them with the confirmed words: they join the history."""
        while self._verified < limit:
            (words, reset), state = mapped[self._verified - base]
            self._remember(self._verified, words, reset)
            self._verified_state = self._seat_state = state
            self._tell_turn()
            del self._ran[self._verified]
            self._verified += 1

    def _ask_digests(self, position: int, batch: list, saved: bool) -> None:
        """Asks the digests that are due and verified. The game's state is the one before `position`: the digest of the frame
        just before is asked as it stands; an older one from the snapshot taken after its frame, when the way back to
        `position` is `saved`."""
        at = position
        while self._digest_due and self._digest_due[0] < self._verified:
            after = self._digest_due[0] + 1
            if after != at:
                if not saved:
                    break                               # with the next batch, which saves the present first
                if position - after >= self.ring:       # its snapshot is gone (never, by the cap: counted, not hidden)
                    self._digest_due.popleft()
                    self.stats['digests_skipped'] += 1
                    continue
                batch.append(pipe.load(after))
                self.stats['loads'] += 1
                at = after
            batch.append(pipe.digest())
            self._digest_asked.append(self._digest_due.popleft())
        if at != position:
            batch.append(pipe.load(position))
            self.stats['loads'] += 1

    def _pause_confirmed(self, upto: int) -> bool:
        """A pause request in a confirmed frame up to `upto` (the live one at most) that was not looked at yet pauses the
        game now, whatever it already ran. True when it did."""
        for frame in range(self._pause_checked, upto + 1):
            if frame not in self._resumed:
                pausers = [seat for seat in range(self.seats)
                           if self._records[seat][frame][1] & pipe.SYS_PAUSE
                           and not (frame and self._records[seat][frame - 1][1] & pipe.SYS_PAUSE)]
                if pausers:
                    self.paused = (frame, pausers)
                    self._host_saw_pause = False
                    self.pauses.append((frame, pausers[0], None))
                    self._tell(pipe.pause(True, self.names[pausers[0]]))
                    return True
            self._pause_checked = frame + 1
        return False

    def _step(self, now: float):
        if not self.rolling:
            return super()._step(now)
        if self._phase == 'linger':
            self._settle()
            return
        if self._phase != 'play' or not self._started(now):
            return
        while self._phase == 'play':
            self._check_resume()
            frame = self.next_run
            if self.settings.last_frame is not None and frame >= self.settings.last_frame:
                self._phase = 'linger'
                self._linger_until = now + LINGER
                self._settle()
                return
            if self.paused is not None:
                return
            if self.game_frame < frame or len(self._records[self.seat]) <= frame:
                return                              # the game has not asked for it yet: decided with the latest records
            confirmed = self._confirmed()
            if self._pause_confirmed(min(confirmed - 1, frame)):
                continue
            if frame - confirmed >= self.cap:       # the cap: no more frames on a guess; the game waits, as on the delay tier
                if self._blocked_since is None:
                    self._blocked_since = now
                    self._blocked_on = min(range(self.seats), key=lambda seat: len(self._records[seat]))
                    self.stats['cap_waits'] += 1
                return
            base, batch = self._verified, []
            mapped = self._mapped(frame)
            self._correct(frame, mapped, batch)
            self._verify(min(confirmed, frame), mapped, base)
            batch.append(pipe.save(frame))
            self.stats['saves'] += 1
            self._ask_digests(frame, batch, saved=True)
            run = mapped[frame - base][0]
            batch.append(pipe.run(frame, run[0], reset=run[1]))
            self._ran[frame] = run
            if frame >= confirmed:
                self.stats['predicted_frames'] += 1
            self._verify(min(confirmed, frame + 1), mapped, base)
            if self._waiting_noticed:
                self._tell(pipe.notice(pipe.NOTICE_RESUMED))
                self._waiting_noticed = False
            self._blocked_since = None
            self.stats['runs'] += 1
            self.next_run = frame + 1
            if self.next_run % self.settings.digest_every == 0 or self.next_run == self.settings.last_frame:
                self._digest_due.append(frame)
                self._ask_digests(self.next_run, batch, saved=False)    # answered after this frame ran, when it is verified
            self._tell(b''.join(batch))             # one write: the correction and the live frame are one batch
            if self.next_run % 32 == 0:
                self._trim()

    def _settle(self) -> None:
        """After the last frame: once every seat's record of it is known, the frames still run on a guess are corrected
        (no live frame follows) and the last digests asked."""
        last = self.next_run
        if self._verified >= last and not self._digest_due:
            return
        if self._confirmed() < last:
            return
        base, batch = self._verified, []
        if base < last:
            mapped = self._mapped(last - 1)
            self._correct(last, mapped, batch)
            self._verify(last, mapped, base)
        batch.append(pipe.save(last))
        self.stats['saves'] += 1
        self._ask_digests(last, batch, saved=True)
        self._tell(b''.join(batch))


def driver_for(game: SessionGame, link: SeatLink, settings: Settings) -> LockstepDriver:
    """The driver of a seat: the delay-lockstep driver itself, unless the settings ask for rollback (then the game's HELLO
    decides the tier inside `RollbackDriver`)."""
    return RollbackDriver(game, link, settings) if settings.rollback else LockstepDriver(game, link, settings)
