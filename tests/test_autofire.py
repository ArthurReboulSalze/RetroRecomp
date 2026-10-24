"""ROM-free regression for the shared keyboard/gamepad pulse policy."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

CHECKS=r'''
#include "autofire.h"
#undef NDEBUG
#include <assert.h>
int main(void) {
    RrAutofire state={0};
    for(unsigned hz=50;hz<=60;hz+=10) {
        state.held=false;unsigned pulses=0;bool previous=false;
        for(uint64_t frame=0;frame<hz;++frame) {
            bool down=rr_autofire(&state,true,true,frame);
            if(down && !previous)++pulses;
            previous=down;
            for(unsigned poll=0;poll<8;++poll)assert(rr_autofire(&state,true,true,frame)==down);
        }
        assert(pulses==hz/2);
    }
    assert(rr_autofire(&state,true,false,100));
    assert(rr_autofire(&state,true,true,101));
    assert(!rr_autofire(&state,true,true,102));
    for(unsigned poll=0;poll<100;++poll)assert(!rr_autofire(&state,true,true,102));
    /* Rewind even inside the same held press, then start again immediately. */
    assert(rr_autofire(&state,true,true,101));
    assert(!rr_autofire(&state,true,true,102));
    assert(!rr_autofire(&state,false,true,102));
    assert(rr_autofire(&state,true,true,102));
    RrAutofire independent={0};
    assert(rr_autofire(&independent,true,true,103));
    assert(!rr_autofire(&state,true,true,103));
    assert(rr_autofire(&state,true,true,104));
    assert(!rr_autofire(&independent,true,true,104));
    return 0;
}
'''


class AutofireTests(unittest.TestCase):
    def test_guest_frame_cadence_in_c_and_cpp(self):
        cmake=shutil.which('cmake')
        if not cmake:
            from retrorecomp.core import toolchain
            try:cmake,_=toolchain()
            except RuntimeError:pass
        if not cmake:self.skipTest('CMake unavailable')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'check.c').write_text(CHECKS,encoding='utf-8')
            (root/'check.cpp').write_text(CHECKS,encoding='utf-8')
            (root/'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.20)\nproject(AutofirePolicy C CXX)\n'
                f'include_directories("{(ROOT/"native").as_posix()}")\n'
                'add_executable(check_c check.c)\nadd_executable(check_cpp check.cpp)\n',encoding='utf-8')
            for command in ([cmake,'-S',str(root),'-B',str(root/'build')],
                            [cmake,'--build',str(root/'build'),'--config','Release']):
                result=subprocess.run(command,capture_output=True,text=True,timeout=120)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            for name in ('check_c','check_cpp'):
                candidates=[root/'build/Release'/(name+'.exe'),root/'build'/name]
                executable=next(p for p in candidates if p.is_file())
                result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
