"""Free a GUI test's Tk objects on the main thread, when the test ends.

A test's root, its widgets, the stand-ins (Mock owners) and the views often point at each other. Left to Python's cycle
collector, a dead Tk interpreter is freed whenever the collector next runs, and that can be in another thread (a view's
cover loader, a netplay worker): freeing a Tk interpreter outside its own thread aborts the whole process with
« Tcl_AsyncDelete: async handler deleted by the wrong thread » (the full suite, 19 Nov 2026).

Call `release_tk(self)` FIRST in setUp, before the root's own addCleanup: cleanups run last first, so this one runs after
root.destroy. It drops the test's own attributes (the ones without a leading underscore, so not unittest's) and collects."""
import gc


def release_tk(case):
    def release():
        for name in [name for name in vars(case) if not name.startswith('_')]:
            delattr(case, name)
        gc.collect()
    case.addCleanup(release)
