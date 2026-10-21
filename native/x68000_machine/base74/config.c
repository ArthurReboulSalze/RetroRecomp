/* Retro-Recomp X68000: machine configuration for the 2014 code.
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Fixed values of this machine profile; no INI file is read or written.
 */
#include "common.h"
#include "prop.h"
#include "dswin.h"

Win68Conf Config;

void LoadConfig(void)
{
   static int loaded = 0;
   if (loaded)
      return;
   loaded = 1;
   Config.SampleRate = RR_SOUND_RATE;
   Config.BufferSize = 50;
   Config.OPM_VOL = 12;
   Config.PCM_VOL = 15;
   Config.MCR_VOL = 13;
   Config.WindowFDDStat = 1;
   Config.MIDI_SW = 1;
   Config.MIDI_Type = 1;
   Config.MIDI_Reset = 1;
   Config.SRAMWarning = 1;
   Config.ToneMap = 0;
   Config.ToneMapFile[0] = 0;
   Config.XVIMode = 0;
   Config.WinStrech = 1;
   Config.Sound_LPF = 1;
   Config.SoundROMEO = 0;
   Config.MIDIDelay = 250;
   Config.MIDIAutoDelay = 1;
   Config.VbtnSwap = 0;
   Config.JoyOrMouse = 1;
   Config.JoyKeyReverse = 0;
   Config.NoWaitMode = 0;
   Config.FrameRate = 1;
   Config.AdjustFrameRates = 1;
   Config.AudioDesyncHack = 0;
   memset(Config.HDImage, 0, sizeof Config.HDImage);
   memset(Config.FDDImage, 0, sizeof Config.FDDImage);
}

void SaveConfig(void)
{
}
