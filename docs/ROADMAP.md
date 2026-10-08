# RetroRecomp roadmap

RetroRecomp 0.18.0 converts supported Master System, Game Gear and original
Game Boy ROMs, and includes experimental NES, Mega Drive and Super Nintendo
profiles. The 16-bit profiles accept only qualified game revisions. The
priorities below describe areas to improve, not compatibility or delivery promises.

| Priority | Work needed |
| --- | --- |
| Broader game coverage | Explore more gameplay paths and guarded RAM variants; reduce reported interpreter fallback. |
| Video and peripherals | Refine hardware timing and edge cases using independent fixtures and game evidence. |
| Gameplay confidence | Extend repeatable scenarios and collect more hands-on validation for supported ROMs. |
| Input response | Measure end-to-end controller latency before making performance claims. |
| NES | Extend mapper, PAL, peripheral and gameplay validation beyond the existing bounded checks. |
| Mega Drive | Qualify more distinct cartridges, diagnose Sonic reference divergence, and add PAL and persistent states. |
| Super Nintendo | Diagnose reference divergence and reduce main-CPU fallback before expanding games, timing modes and saves. |

## Improvement loop

We want to explore more paths using a local decision or vision model:
observation, input choice, deterministic replay, guarded compilation and
comparison before regeneration. A stopping threshold could combine native
coverage, regression stability and exploration budget. More explored paths
do not prove complete gameplay or hardware fidelity.

The current version reuses verified observations and checks candidates. The
AI player/autonomous exploration loop is not implemented. No model weights,
API credentials or online-model integration are distributed.
