"""A Tk variable, image, font or root freed in a worker thread is released later on the Tk thread (no Tcl_AsyncDelete abort)."""
import gc
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path

from retrorecomp import tk_threads

ROOT = Path(__file__).resolve().parents[1]


class TkThreadsTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f'no display: {error}')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        tk_threads.install()
        tk_threads.release_deferred()

    def test_a_variable_dropped_in_a_worker_waits_for_the_tk_thread(self):
        holder = [tk.StringVar(self.root, value='x', name='rr_thread_var')]
        self.assertEqual(self.root.globalgetvar('rr_thread_var'), 'x')
        worker = threading.Thread(target=holder.clear)        # the last reference goes away in the worker
        worker.start(); worker.join()
        self.assertEqual(tk_threads.pending(), 1)
        self.assertEqual(self.root.globalgetvar('rr_thread_var'), 'x')    # not touched from the worker
        self.assertEqual(tk_threads.release_deferred(), 1)
        with self.assertRaises(tk.TclError):
            self.root.globalgetvar('rr_thread_var')                      # forgotten, on this thread
        gc.collect()
        self.assertEqual(tk_threads.pending(), 0)

    def test_an_image_dropped_in_a_worker_is_deleted_later(self):
        holder = [tk.PhotoImage(master=self.root, width=2, height=2)]
        name = holder[0].name
        worker = threading.Thread(target=holder.clear)
        worker.start(); worker.join()
        self.assertIn(name, self.root.image_names())
        tk_threads.release_deferred()
        self.assertNotIn(name, self.root.image_names())

    def test_on_the_main_thread_nothing_is_deferred(self):
        var = tk.IntVar(self.root, value=3, name='rr_main_var')
        del var
        self.assertEqual(tk_threads.pending(), 0)
        with self.assertRaises(tk.TclError):
            self.root.globalgetvar('rr_main_var')


    def test_a_dead_root_s_interpreter_waits_for_the_next_root_on_the_main_thread(self):
        tk_threads.release_deferred()
        other = tk.Tk()
        other.withdraw()
        other.destroy()
        del other                                                       # its __del__ parks the interpreter
        self.assertEqual(tk_threads.parked(), 1)
        held = []
        third = tk.Tk()                                                 # a new root frees it first, on this thread
        third.withdraw()
        self.addCleanup(third.destroy)
        self.assertEqual(tk_threads.parked(), 0)
        fourth = tk.Tk()
        fourth.withdraw()
        held.append(fourth.tk)                                          # something still holds this one: it stays parked
        fourth.destroy()
        del fourth
        self.assertEqual(tk_threads.release_deferred(), 0)
        self.assertEqual(tk_threads.parked(), 1)
        held.clear()
        self.assertEqual(tk_threads.release_deferred(), 1)
        self.assertEqual(tk_threads.parked(), 0)

    def test_tk_later_installs_the_guard_when_imported(self):
        from retrorecomp import tk_later                               # every window module imports it
        self.assertTrue(tk_later.tk_threads is tk_threads)
        self.assertTrue(getattr(tk.Tk, '_retro_recomp_guarded', False))


    def test_a_pillow_picture_dropped_in_a_worker_is_deleted_later(self):
        from PIL import Image, ImageTk
        holder = [ImageTk.PhotoImage(Image.new('RGB', (2, 2)), master=self.root)]
        name = str(holder[0])
        worker = threading.Thread(target=holder.clear)                 # its __del__ would call Tcl from the worker
        worker.start(); worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertIn(name, self.root.image_names())
        tk_threads.release_deferred()
        self.assertNotIn(name, self.root.image_names())

    def test_a_destroyed_root_keeps_no_python_callback_so_its_owner_is_freed(self):
        import weakref

        class Owner:
            def changed(self, *_):
                pass
        other = tk.Tk()
        other.withdraw()
        owner = Owner()
        owner.root, owner.value = other, tk.StringVar(other)          # the window object and its variable
        owner.value.trace_add('write', owner.changed)                   # held by Tcl, not by a widget
        other.bind('<Map>', lambda event: owner.changed())
        gone = weakref.ref(owner)
        other.destroy()
        commands = [name for name in other.tk.splitlist(other.tk.call('info', 'commands')) if name[:1].isdigit()]
        self.assertEqual(commands, [])
        del owner, other
        gc.collect()
        self.assertIsNone(gone())                                       # its variable's __del__ found its command gone, silently
        tk_threads.release_deferred()

    def test_a_destroyed_root_leaves_no_timer_to_run_under_another_root(self):
        """A timer still queued when its root goes would run at the next root's update() with its command gone
        (« invalid command name "…poll" », about 115 per full suite before 27 November 2026)."""
        from retrorecomp import tk_later
        other = tk.Tk()
        other.withdraw()
        label = tk.Label(other)
        ran = []
        tk_later.later(label, 1, lambda: ran.append(1))
        other.after(1, lambda: ran.append(2))
        self.assertEqual(len(other.tk.splitlist(other.tk.call('after', 'info'))), 2)
        other.destroy()
        self.assertEqual(other.tk.splitlist(other.tk.call('after', 'info')), ())
        for _ in range(5):                    # Tcl prints its « invalid command name » on the C stderr: the queue is what is checked
            self.root.update()
            time.sleep(0.005)
        self.assertEqual(ran, [])
        del other, label
        gc.collect()
        tk_threads.release_deferred()

# A destroyed root in a reference cycle, freed by the cycle collector in a worker thread (what the full suite hit twice on
# 22 Nov 2026: Tcl deletes the interpreter from the wrong thread and aborts the process, exit 3, no traceback). With a font
# too, which holds the interpreter as well. argv: the repository, then "guard" to import tk_later first.
GC_IN_A_WORKER = r'''
import gc, sys, threading, tkinter as tk
from tkinter import font
sys.path.insert(0, sys.argv[1])
if sys.argv[2] == 'guard':
    from retrorecomp import tk_later
gc.disable()
class Owner:
    pass
for _ in range(3):
    root = tk.Tk()
    root.withdraw()
    owner = Owner()
    owner.root, root.owner = root, owner
    owner.font = font.Font(root=root, family='Arial', size=9)
    tk.Label(root, text='x', font=owner.font).pack()
    root.update()
    root.destroy()
    del root, owner
worker = threading.Thread(target=gc.collect)
worker.start()
worker.join()
gc.collect()
print('alive')
'''


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'needs a Tk display (kept hidden)')
class NoAbortWhenAWorkerCollectsARoot(unittest.TestCase):
    # In a child process: an abort there is a failed test, not a dead suite.
    def collect_in_a_worker(self, mode):
        return subprocess.run([sys.executable, '-B', '-c', GC_IN_A_WORKER, str(ROOT), mode], capture_output=True, text=True,
                              timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def test_with_the_guard_the_process_lives(self):
        result = self.collect_in_a_worker('guard')
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'alive'), result.stderr[-2000:])

    def test_without_it_the_same_script_aborts(self):
        # The positive control: the child reproduces the abort the guard prevents.
        result = self.collect_in_a_worker('none')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Tcl_AsyncDelete', result.stderr)


if __name__ == '__main__':
    unittest.main()
