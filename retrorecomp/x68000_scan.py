"""Bounded deterministic exploration of computer inputs, independent cold boots.

Unlike a joystick-only console scan, these routes also click the mouse and
leave configuration screens with Escape. They are discovery inputs, never
substitutes for fresh native/reference comparisons or full-game validation.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScanRoute:
    name: str
    frames: int
    events: tuple


def exploration_routes(frames, *, mouse_controls=False):
    count=max(4000,min(int(frames),6000))
    mouse_count=10000 if mouse_controls else count
    mouse=[]
    targets=((256,256),(448,480),(96,96),(448,96),(96,448))
    for n,frame in enumerate(range(1100,mouse_count-220,340)):
        x,y=targets[n%len(targets)]
        # Saturate toward the origin, then visit several screen regions. A
        # tiny oscillation near (0,0) never activates many computer menus.
        mouse += [(frame,frame+24,'mouse',0,-64),(frame,frame+24,'mouse',1,-64),
                  (frame+36,frame+36+x//8,'mouse',0,8),
                  (frame+36,frame+36+y//8,'mouse',1,8),
                  (frame+112,frame+118,'mouse',2,1),
                  (frame+180,frame+186,'key',13,1)]
        if n%5==4:mouse.append((frame+150,frame+154,'mouse',3,1))
    keys=[]
    for n,frame in enumerate(range(1400,count-240,480)):
        keys += [(frame,frame+4,'key',27,1),
                 (frame+30,frame+36,'key',13,1),
                 (frame+60,frame+66,'key',32,1),
                 (frame+90,frame+230,'joy',0,1),
                 (frame+100,frame+220,'joy',7 if n%2 else 6,1),
                 (frame+120,frame+170,'joy',4,1)]
    return (ScanRoute('mouse',mouse_count,tuple(mouse)),ScanRoute('keyboard',count,tuple(keys)))


LONG_ROUTE_FRAMES=36000
LONG_ROUTE_COUNT=3


def long_routes(identity, *, mouse_controls=False, count=LONG_ROUTE_COUNT, frames=LONG_ROUTE_FRAMES):
    """Long varied play for discovery: later stages, demos and code the game
    builds in RAM only after several minutes. Seeds come from the exact source
    identity, so every conversion of the same set replays the same routes."""
    import random
    routes=[]
    for index in range(count):
        rng=random.Random(f'x68-long:{identity}:{index}')
        rows,frame=[],900
        while frame<frames-200:
            roll=rng.random()
            if roll<0.45:                      # move, often firing
                length=rng.randint(20,160)
                rows.append((frame,frame+length,'joy',rng.choice((4,5,6,7)),1))
                if rng.random()<0.7:rows.append((frame,frame+length,'joy',rng.choice((0,8)),1))
            elif roll<0.7:                     # button taps
                rows.append((frame,frame+rng.randint(3,12),'joy',rng.choice((0,1,8)),1))
            elif roll<(0.8 if mouse_controls else 0.85):  # menu keys
                rows.append((frame,frame+6,'key',rng.choice((13,32,27,49,50)),1))
            else:                              # mouse move and click
                rows.append((frame,frame+20,'mouse',rng.choice((0,1)),rng.choice((-24,-8,8,24))))
                if rng.random()<0.5:rows.append((frame+22,frame+28,'mouse',2,1))
            frame+=rng.randint(30,120)
        routes.append(ScanRoute(f'long-{index+1}',frames,tuple(rows)))
    return tuple(routes)
