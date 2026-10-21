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
