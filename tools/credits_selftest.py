"""Check actual bundled MOD decoding, optionally compare ChipLoom's full libxmp.

Native library must first be built by tools/build_credits_audio.py. No ROMs,
game exports or user settings are read. --device additionally exercises audio.
"""
import argparse
import array
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.credits_music import TRACKS, Decoder, library_path


def reference_decoder(path, data):
    lib = C.CDLL(str(path))
    for name,result,args in (
        ('create_context',C.c_void_p,()),
        ('load_module_from_memory',C.c_int,(C.c_void_p,C.c_void_p,C.c_long)),
        ('start_player',C.c_int,(C.c_void_p,C.c_int,C.c_int)),
        ('set_player',C.c_int,(C.c_void_p,C.c_int,C.c_int)),
        ('play_buffer',C.c_int,(C.c_void_p,C.c_void_p,C.c_int,C.c_int)),
        ('end_player',None,(C.c_void_p,)),('release_module',None,(C.c_void_p,)),
        ('free_context',None,(C.c_void_p,)),
    ):
        func=getattr(lib,'xmp_'+name);func.restype=result;func.argtypes=args
    handle=lib.xmp_create_context()
    buffer=C.create_string_buffer(data)
    assert lib.xmp_load_module_from_memory(handle,buffer,len(data))==0
    assert lib.xmp_start_player(handle,48000,0)==0
    assert lib.xmp_set_player(handle,2,2)==0 # spline
    assert lib.xmp_set_player(handle,1,70)==0
    return lib,handle,buffer


def check_percussion_events():
    """Synthetic MOD: held voices, sample-only rows, note delay and portamento."""
    data=bytearray(1084+1024+128*3)
    for slot,name in enumerate((b'Kick',b'Snare',b'Noise tick')):
        offset=20+slot*30
        data[offset:offset+len(name)]=name
        data[offset+22:offset+24]=(64).to_bytes(2,'big')
        data[offset+25]=64
        data[1084+1024+slot*128:1084+1024+(slot+1)*128]=bytes((40,216))*64
    data[950]=1; data[1080:1084]=b'M.K.'
    def event(row,ins,period,fx=0,param=0):
        offset=1084+row*16
        data[offset:offset+4]=bytes(((ins&16)|(period>>8),period&255,(ins&15)*16+fx,param))
    event(0,1,428)
    event(2,1,0)           # sample without a note: no new hit
    event(3,1,428)
    event(4,2,428,14,0xd3) # delayed snare
    event(5,2,214,3,8)     # slide the existing voice, do not retrigger it
    event(6,3,428,12,0)    # silent note
    decoder=Decoder(bytes(data))
    try:
        decoder.render(48000)
        assert decoder.beats()[:3]==(2,1,0),decoder.beats()
    finally: decoder.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path)
    parser.add_argument('--device',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    check_percussion_events()
    results=[]
    for name in TRACKS:
        data=(ROOT/'MEDIAS/trackers_chiploom'/name).read_bytes()
        decoder=Decoder(data)
        reference=reference_decoder(args.reference,data) if args.reference else None
        digest=hashlib.sha256()
        peak=0
        positions=set()
        try:
            # Three minutes cover a complete cycle of each supplied composition.
            for _ in range(180):
                pcm=decoder.render(48000)
                digest.update(pcm)
                peak=max(peak,max(abs(x) for x in array.array('h',pcm)))
                positions.add(decoder.info()[:3])
                if reference:
                    lib,handle,_=reference
                    expected=C.create_string_buffer(len(pcm))
                    assert lib.xmp_play_buffer(handle,expected,len(pcm),0)==0
                    assert expected.raw==pcm, (name,'PCM differs from full libxmp')
            assert 0<peak<=32768 and len(positions)>15, name
            beats = decoder.beats()
            assert all(count>20 for count in beats[:3]), (name,beats)
        finally:
            decoder.close()
            if reference:
                lib.xmp_end_player(handle);lib.xmp_release_module(handle);lib.xmp_free_context(handle)
        results.append(dict(track=name,bytes=len(data),seconds=180,pcm_sha256=digest.hexdigest(),peak=peak,
                            reference_equal=bool(reference),positions=len(positions),percussion_hits=beats[:3]))
        if args.device:
            decoder=Decoder(data)
            try:
                decoder.mute(True);decoder.start();time.sleep(.2)
                before=decoder.info()
                decoder.mute(False);time.sleep(.4)
                after=decoder.info()
                assert before[:3]!=after[:3],name
                decoder.mute(True)
            finally:decoder.close()
    try:
        bad=Decoder(b'\x00'*1084)
    except ValueError: pass
    else:
        bad.close();raise AssertionError('Malformed MOD was accepted')
    proof={'library_bytes':library_path().stat().st_size,'tracks':results,
           'percussion_events_checked':True,'device_checked':args.device}
    if args.output:args.output.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(proof,indent=2))


if __name__=='__main__':main()
