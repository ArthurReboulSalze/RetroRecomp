"""Reject incomplete geometry and keep pinned engine adaptation fail-closed."""
import unittest
from pathlib import Path
from retrorecomp import snes_video, supernintendo
from retrorecomp.console16 import reference_differences
from retrorecomp.core import ConversionError

class SnesVideoTests(unittest.TestCase):
    def test_geometry_is_required_and_modes_are_preserved(self):
        profile={'video_scope':'standard_ppu'}
        for width in (256,512):
            for height in (224,239):
                for density in (1,2):
                    valid=dict(frames=3600,visible_frames=1,pcm_nonzero=1,
                        visible_width=width,active_raster_height=height,
                        visible_height=height*density,output_row_density=density,captured_rows=height)
                    supernintendo.validate_activity(profile,[valid])
                    for key in ('visible_width','active_raster_height','visible_height','output_row_density','captured_rows'):
                        bad=dict(valid);bad.pop(key)
                        with self.subTest(key=key),self.assertRaises(ConversionError):
                            supernintendo.validate_activity(profile,[bad])
                    with self.assertRaises(ConversionError):
                        supernintendo.validate_activity(profile,[dict(valid,captured_rows=height-1)])
        with self.assertRaises(ConversionError):
            supernintendo.validate_activity(profile,[dict(valid,pcm_nonzero=0)])
    def test_geometry_mismatch_is_a_reference_failure(self):
        a=dict(captured_rows=239,visible_width=512,visible_height=478,active_raster_height=239,
               output_row_density=2,field_parity=1)
        for key in a:
            b=dict(a);b[key]+=1
            self.assertIn(key,reference_differences('snes',a,b))
    def test_unrecognized_engine_hooks_fail_closed(self):
        for adapt in (snes_video.legacy,snes_video.ppu,snes_video.frame_driver,snes_video.bus):
            with self.assertRaises(ConversionError):adapt('unknown engine source')

if __name__=='__main__':unittest.main()
