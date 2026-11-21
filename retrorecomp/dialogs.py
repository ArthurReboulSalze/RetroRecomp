"""Shared converter window placement (no generated-game dependency).

Every converter window is sized and placed here (Arthur, 20 Nov 2026: on a 1280-wide screen the Help window opened half off it):

- `work_area` is the usable part of the screen the window is on: on Windows the work area of its monitor (taskbar excluded,
  multi-monitor aware, in the same pixels as Tk since both live in this process); elsewhere Tk's screen less a panel's height.
- `screen_room` is the room left for a window's inside: the work area less a margin and the window's frame (title bar, borders).
- `place_window` sizes a window within that room and centres it on its parent (or on the work area), frame included.
- `watch_windows` checks every converter window once it is shown: whatever made it (a size measured from its content, a position
  computed by hand), its frame is brought back inside the work area, shrunk if it is larger, its minimum size lowered to fit.

Sizes written for 96 dpi go through `ui_fonts.scaled` first (unchanged on Windows, Tk's factor on Linux), then the clamp: the room
always wins, at every scale."""
import os

from .ui_fonts import scaled

MARGIN = 12                 # pixels kept free between a window's frame and the edge of the work area
FRAME = (16, 40)            # a window's frame around its inside before it is shown (borders, title bar); read for real once shown
PANEL = 50                  # where the screen's own size is all we know (Linux): room for a panel or a taskbar


def _monitor_work_area(reference):
    """Windows: (left, top, right, bottom) of the work area of the monitor `reference` is on (or, not shown yet, the monitor under
    the pointer, where the player just clicked). None elsewhere or on failure."""
    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]

        user = ctypes.WinDLL('user32')
        user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user.MonitorFromWindow.restype = wintypes.HANDLE
        user.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user.MonitorFromPoint.restype = wintypes.HANDLE
        user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        nearest = 2                                       # MONITOR_DEFAULTTONEAREST
        monitor = None
        if reference is not None and reference.winfo_ismapped():
            top = reference.winfo_toplevel()
            monitor = user.MonitorFromWindow(int(top.wm_frame(), 16), nearest)
        if not monitor:
            x, y = reference.winfo_pointerxy() if reference is not None else (0, 0)
            monitor = user.MonitorFromPoint(wintypes.POINT(x, y), nearest)
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if not monitor or not user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        work = info.rcWork
        if work.right - work.left < 200 or work.bottom - work.top < 200:
            return None
        return work.left, work.top, work.right, work.bottom
    except (OSError, AttributeError, ValueError, TypeError):
        return None


def work_area(reference):
    """(left, top, right, bottom) of the usable screen around `reference` (a widget): see the module's notes."""
    area = _monitor_work_area(reference)
    if area:
        return area
    left, top = reference.winfo_vrootx(), reference.winfo_vrooty()
    return left, top, left + reference.winfo_screenwidth(), top + reference.winfo_screenheight() - PANEL


def screen_room(reference):
    """Usable width and height for a window's inside on the screen `reference` is on: the work area less the margins and the frame
    (small laptops run at 1280x720 or 1366x768)."""
    left, top, right, bottom = work_area(reference)
    return right - left - 2 * MARGIN - FRAME[0], bottom - top - 2 * MARGIN - FRAME[1]


def place_window(window, width, height, parent=None):
    """Size `window`'s inside to `width` x `height` screen pixels, clamped to the room, and centre it on `parent` when `parent` is
    shown (on the work area otherwise), its frame kept inside the work area. Returns the size it was given."""
    reference = parent if parent is not None and parent.winfo_ismapped() else None
    left, top, right, bottom = work_area(reference if reference is not None else (parent or window))
    room_width, room_height = right - left - 2 * MARGIN - FRAME[0], bottom - top - 2 * MARGIN - FRAME[1]
    width, height = max(1, min(int(width), room_width)), max(1, min(int(height), room_height))
    outer_width, outer_height = width + FRAME[0], height + FRAME[1]
    if reference is not None:
        reference.update_idletasks()
        centre_x = reference.winfo_rootx() + reference.winfo_width() // 2
        centre_y = reference.winfo_rooty() + reference.winfo_height() // 2
    else:
        centre_x, centre_y = (left + right) // 2, (top + bottom) // 2
    x = max(left + MARGIN, min(centre_x - outer_width // 2, right - MARGIN - outer_width))
    y = max(top + MARGIN, min(centre_y - outer_height // 2, bottom - MARGIN - outer_height))
    # '+-1280' is a position LEFT of the screen's origin (a monitor on the left); '-1280' would count from the right edge.
    window.geometry(f'{width}x{height}+{x}+{y}')
    return width, height


def center_dialog(panel, parent, width, height, measured=False):
    """Place `panel` centred on `parent`. `width` and `height` are sizes written for 96 dpi and are scaled to the screen (ui_fonts.scaled:
    unchanged on Windows). Pass measured=True for a size taken from winfo_reqwidth() or winfo_reqheight(): it is already in screen
    pixels. Either way the window is clamped to the room of the screen it opens on (place_window)."""
    parent.update_idletasks()
    if not measured:
        width, height = scaled(parent, width), scaled(parent, height)
    place_window(panel, width, height, parent)


def fit_screen(master, pixels, room):
    """A 96 dpi size scaled to the screen (ui_fonts.scaled), never beyond `room`: on a screen smaller than the window was written
    for, the room wins (a window larger than its screen could not be moved back onto it)."""
    return max(1, min(scaled(master, pixels), room))


def fit_size(window, width, height):
    """(width, height) written for 96 dpi, scaled and clamped to the room of `window`'s screen: a window's minimum size."""
    room_width, room_height = screen_room(window)
    return fit_screen(window, width, room_width), fit_screen(window, height, room_height)


def _geometry(window):
    """(width, height, x, y) of `window`'s `wm geometry`."""
    size, x, y = window.wm_geometry().replace('+-', '+~').replace('-', '+~').split('+')
    width, height = (int(part) for part in size.split('x'))
    return width, height, int(x.replace('~', '-')), int(y.replace('~', '-'))


def keep_on_screen(window):
    """Bring a shown window's whole frame (title bar and bottom included) inside the work area of the monitor it is on: moved,
    shrunk when it is larger than the room (its minimum size lowered first, or Tk would refuse). Nothing changes for a window that
    already fits."""
    try:
        if not window.winfo_exists() or not window.winfo_ismapped() or window.wm_overrideredirect():
            return
        window.update_idletasks()
        width, height, x, y = _geometry(window)
        if window.wm_state() != 'normal':           # zoomed (maximised) or iconic: the system placed it
            return
        left, top, right, bottom = work_area(window)
        # The frame around the inside, as it really is now: left border = right border = bottom border on Windows and X11.
        border = max(0, window.winfo_rootx() - x)
        title = max(0, window.winfo_rooty() - y)
        frame_width, frame_height = 2 * border, title + border
        room_width = right - left - 2 * MARGIN - frame_width
        room_height = bottom - top - 2 * MARGIN - frame_height
        new_width, new_height = min(width, room_width), min(height, room_height)
        minimum_width, minimum_height = window.wm_minsize()
        if minimum_width > room_width or minimum_height > room_height:
            window.wm_minsize(min(minimum_width, room_width), min(minimum_height, room_height))
        outer_width, outer_height = new_width + frame_width, new_height + frame_height
        new_x = max(left + MARGIN, min(x, right - MARGIN - outer_width))
        new_y = max(top + MARGIN, min(y, bottom - MARGIN - outer_height))
        if (new_width, new_height, new_x, new_y) != (width, height, x, y):
            window.geometry(f'{new_width}x{new_height}+{new_x}+{new_y}')
    except Exception:       # a window closing under us: nothing to keep
        return


def window_shown(root, window):
    """A window was mapped (watch_windows): check it once, when Tk is next idle (keep_on_screen)."""
    try:
        if window is not window.winfo_toplevel() or getattr(window, '_rr_kept_on_screen', False):
            return
        window._rr_kept_on_screen = True
        # Scheduled on the main window, never on `window`: tkinter names a callback's Tcl command after the Python
        # function's id and deletes the commands of a widget when it is destroyed, but not its pending idle script.
        # A dialog closed before its idle check ran left that script queued, and the next dialog's button command,
        # given the same freed id and so the same name, was pressed by it: the Stop dialog answered « Stop now » by
        # itself (gui_smoke, 21 Nov 2026). keep_on_screen skips a window that no longer exists.
        root.after_idle(keep_on_screen, window)
    except Exception:
        return


def watch_windows(root):
    """Check every converter window once, when it is first shown (the main window and every Toplevel, not tooltips or menus): see
    keep_on_screen. Install once, on the main window."""
    if getattr(root, '_rr_watching_windows', False):
        return
    root._rr_watching_windows = True

    def shown(event):
        window_shown(root, event.widget)

    root.bind_class('Toplevel', '<Map>', shown, add='+')
    root.bind_class('Tk', '<Map>', shown, add='+')


def popup_menu(menu, x, y):
    """Show a context menu at (x, y), screen coordinates. On Windows and macOS the menu is native: tk_popup waits until
    it closes and any outside click closes it, so the grab it leaves is released after. On X11 (Linux) tk_popup returns
    at once and the menu closes on an outside click or Escape only while it holds its grab: releasing it there left the
    menu open after a click elsewhere (Arthur, 13 Nov 2026, on a Linux laptop). Every menu of the window goes here."""
    if menu.tk.call('tk', 'windowingsystem') == 'x11':
        menu.tk_popup(x, y)
        return
    try:
        menu.tk_popup(x, y)
    finally:
        menu.grab_release()
