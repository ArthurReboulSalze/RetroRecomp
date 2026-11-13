"""Shared converter dialog placement (no generated-game dependency)."""


def screen_room(parent):
    """Usable width and height for a window: the screen minus a margin for
    the taskbar and the title bar (small laptops run at 1280x720 or 1366x768)."""
    return parent.winfo_screenwidth() - 40, parent.winfo_screenheight() - 90


def center_dialog(panel, parent, width, height):
    parent.update_idletasks()
    room_width, room_height = screen_room(parent)
    width = min(width, room_width)
    height = min(height, room_height)
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    # Keep the whole window on the screen, title bar included.
    x = max(parent.winfo_vrootx() + 10, min(x, parent.winfo_vrootx() + room_width + 30 - width))
    y = max(parent.winfo_vrooty() + 30, min(y, parent.winfo_vrooty() + room_height + 50 - height))
    panel.geometry(f'{width}x{height}{x:+d}{y:+d}')


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
