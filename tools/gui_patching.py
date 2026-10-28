"""Patch a name of the window wherever its code lives (tests and self-tests).

The window is split by responsibility into `retrorecomp/gui.py` and `retrorecomp/gui_*.py`
(docs/ARCHITECTURE.md). A name such as `save_preferences` or `SENDING_AVAILABLE` is looked up in
the module of the code that uses it, so patching it in one module would miss the others.
`patch_gui(name, ...)` takes the arguments of `unittest.mock.patch`, replaces the name in every
window module that has it, with one shared replacement, and works as a context manager and
through `start()` / `stop()`.
"""
from __future__ import annotations

import contextlib
import importlib
from pathlib import Path
from unittest.mock import DEFAULT, patch

PACKAGE = Path(__file__).resolve().parents[1] / 'retrorecomp'


def gui_module_names() -> list[str]:
    """`retrorecomp.gui` and its `gui_*` modules, by name."""
    return ['retrorecomp.gui'] + sorted('retrorecomp.' + path.stem for path in PACKAGE.glob('gui_*.py'))


def gui_modules() -> list:
    return [importlib.import_module(name) for name in gui_module_names()]


def gui_source() -> str:
    """The source of the whole window: gui.py and every gui_*.py, for tests that read the code."""
    paths = [PACKAGE / 'gui.py'] + sorted(PACKAGE.glob('gui_*.py'))
    return '\n'.join(path.read_text(encoding='utf-8') for path in paths)


class patch_gui:
    def __init__(self, name, new=DEFAULT, **options):
        self.name, self.new, self.options = name, new, options
        self._stack = None

    def start(self):
        stack = contextlib.ExitStack()
        owners = [module for module in gui_modules() if hasattr(module, self.name)]
        if not owners:
            raise AttributeError(f'no window module has {self.name!r}')
        value, options = self.new, self.options
        try:
            for module in owners:
                result = stack.enter_context(patch.object(module, self.name, value, **options))
                if value is DEFAULT:
                    value, options = result, {}   # the other modules share the mock made for the first
        except BaseException:
            stack.close()
            raise
        self._stack = stack
        return value

    def stop(self):
        stack, self._stack = self._stack, None
        if stack is not None:
            stack.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False
