"""Shared converter dialog placement (no generated-game dependency)."""


def center_dialog(panel, parent, width, height):
    parent.update_idletasks()
    width = min(width, max(640, parent.winfo_screenwidth() - 60))
    height = min(height, max(460, parent.winfo_screenheight() - 100))
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    # A short parent must not place the title bar above the desktop.
    y = max(parent.winfo_vrooty() + 30, y)
    panel.geometry(f'{width}x{height}{x:+d}{y:+d}')
