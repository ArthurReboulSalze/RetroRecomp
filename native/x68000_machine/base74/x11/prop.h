/* Retro-Recomp X68000 compat: machine configuration (Config).
 *
 * Copyright (c) 2026 Retro-Recomp contributors. MIT License (see LICENSE).
 *
 * Fields read by the kept 2014 machine code, plus the fields our glue sets.
 * Values are filled by native/x68000_machine (no INI file is read).
 */
#ifndef RR_BASE74_PROP_H
#define RR_BASE74_PROP_H

#include "common.h"

typedef struct {
   DWORD SampleRate;
   DWORD BufferSize;
   int OPM_VOL;
   int PCM_VOL;
   int MCR_VOL;
   int WindowFDDStat;
   int MIDI_SW;
   int MIDI_Type;
   int MIDI_Reset;
   int SRAMWarning;
   char HDImage[16][MAX_PATH];
   int ToneMap;
   char ToneMapFile[MAX_PATH];
   int XVIMode;
   int WinStrech;
   int Sound_LPF;
   int SoundROMEO;
   int MIDIDelay;
   int MIDIAutoDelay;
   char FDDImage[2][MAX_PATH];
   int VbtnSwap;
   int JoyOrMouse;
   int JoyKeyReverse;
   int NoWaitMode;
   BYTE FrameRate;
   /* Glue-side settings (fixed for this machine profile). */
   int AdjustFrameRates;
   int AudioDesyncHack;
   int MenuFontSize;
   int joy1_select_mapping;
   int save_fdd_path;
   int save_hdd_path;
   int clockmhz;
   int ram_size;
   int JOY_TYPE[2];
} Win68Conf;

extern Win68Conf Config;

void LoadConfig(void);
void SaveConfig(void);

#endif
