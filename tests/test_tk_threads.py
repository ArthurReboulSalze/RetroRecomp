"""A Tk variable or image freed in a worker thread is released later on the Tk thread (no Tcl_AsyncDelete abort)."""
import gc
import threading
import tkinter as tk
import unittest

from retrorecomp import tk_threads


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


if __name__ == '__main__':
    unittest.main()
