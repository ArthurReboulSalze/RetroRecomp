# Controls

| Key | Action |
| --- | --- |
| F1 | Restart |
| F2 | Control mappings |
| F3 | Next filter: sharp, bilinear, Scale2x, scanlines |
| F4 | Integer-scaled fullscreen/window |
| F6 | English/French |
| H | Help |
| P / Enter / keypad Enter | Pause/resume |
| Esc | Close a menu or quit |

In F2, Enter selects a binding instead of pausing. Left/Right chooses the
player, Tab switches keyboard/gamepad, Up/Down selects a row, and Enter begins
capture. Press the desired key or the selected player's controller button.
Esc cancels capture; D restores that player's defaults for the input type.
C on the gamepad page swaps controller assignments.

| Player | Directions | Buttons | Menu | Restart |
| --- | --- | --- | --- | --- |
| J1 keyboard | Arrows | Z / X | P; Enter also available | F1 |
| J2 keyboard | Keypad 5 / 2 / 1 / 3 | Keypad 8 / 9 | Keypad 7 | Disabled |
| Each gamepad | D-pad / left stick | A / B | Start/Menu | Select/Back, J1 only |

Start/Menu and J1 Select/Reset are configurable on both keyboard and gamepad
pages. A button used for gameplay must be freed before serving a system action.
J2 has no reset row; old J2 reset entries are ignored and removed. J2 binding
details appear only on its mapping page.

The first controller is J1 and the next J2; swapping supports one gamepad for
J2 while J1 uses the keyboard. Settings are shared in `datas/Retro-Recomp.ini`.
Disconnecting one controller keeps the other assigned to its player.

No save states. Fullscreen hides interpreter overlays, not counters. The left
hardware mask is cropped automatically when the rendered frame requests it;
there is no F7/manual switch.
