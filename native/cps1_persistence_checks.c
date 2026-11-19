/* Checks of the EEPROM saves of the CPS-1.5 and CPS-2 boards (native/cps1_persistence.c) against a stand-in for the board's EEPROM calls: a first
 * run with no file, a save written off the frame path when the contents have been stable for a second (and at once when play ends), a second
 * run that loads it, and a file that cannot be used (damaged, or
 * written for another set) which is left alone and never written over. The file is written beside this program (datas/saves). Built by
 * tools/cps1_persistence_selftest.py. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef _WIN32
#include <time.h>
#endif
#include "platform_io.h"
#include "cps1_eeprom.h"
#include "cps1_persistence.h"

static cps1_eeprom chip;
size_t cps1_eeprom_size(void) { return CPS1_EEPROM_BYTES; }
const uint8_t *cps1_eeprom_data(void) { return chip.data; }
int cps1_eeprom_load(const uint8_t *data, size_t size) { if (size != CPS1_EEPROM_BYTES) return 0; memcpy(chip.data, data, size); chip.changed = 0; return 1; }
int cps1_eeprom_changed(void) { return cps1_eeprom_take_changed(&chip); }

static unsigned passed, failed;
static void expect(const char *what, int ok)
{
    if (ok) ++passed; else { ++failed; fprintf(stderr, "FAIL: %s\n", what); }
}

static void sleep_ms(unsigned ms)
{
#ifdef _WIN32
    Sleep(ms);
#else
    struct timespec t = {ms / 1000, (long)(ms % 1000) * 1000000L};
    nanosleep(&t, NULL);
#endif
}
static int file_appears_within(unsigned ms)
{
    wchar_t path[32768];
    rr_cps1_save_path(path, 32768);
    for (unsigned waited = 0; waited <= ms; waited += 50) {
        if (rr_exists(path)) return 1;
        sleep_ms(50);
    }
    return 0;
}
static void blank(void) { cps1_eeprom_reset(&chip, 12); }
static void edit_file(long offset, int value)
{
    wchar_t path[32768];
    rr_cps1_save_path(path, 32768);
    FILE *file = rr_fopen(path, L"r+b");
    if (!file) return;
    fseek(file, offset, SEEK_SET);
    fputc(value, file);
    fclose(file);
}
static void remove_file(void)
{
    wchar_t path[32768];
    if (rr_cps1_save_path(path, 32768)) rr_remove(path);
}

int main(void)
{
    remove_file();
    blank();
    expect("no file: the run starts and the EEPROM stays blank", rr_cps1_save_begin() && chip.data[3] == 0xff);
    rr_cps1_save_frame();
    expect("nothing is written while nothing changed", rr_cps1_save_close());
    rr_cps1_save_begin();                         /* play again, the file still absent */
    chip.data[3] = 0x42; chip.changed = 1;
    rr_cps1_save_frame();                         /* the game changed a cell: the frame does not wait for the disk */
    wchar_t path[32768];
    rr_cps1_save_path(path, 32768);
    expect("the frame writes nothing", !rr_exists(path));
    expect("the worker writes it once the contents are stable", file_appears_within(4000));
    FILE *file = rr_fopen(path, L"rb");
    expect("the save is readable", file != NULL);
    if (file) fclose(file);
    expect("closing writes nothing more to say", rr_cps1_save_close());

    blank();
    expect("a second run loads it", rr_cps1_save_begin() && chip.data[3] == 0x42 && chip.data[4] == 0xff);
    chip.data[5] = 0x77; chip.changed = 1;        /* a change in the last frames: ending play writes it at once */
    expect("closing writes the last contents", rr_cps1_save_close());
    blank();
    expect("and a third run loads them", rr_cps1_save_begin() && chip.data[3] == 0x42 && chip.data[5] == 0x77);
    rr_cps1_save_close();

    edit_file(200, 0x55);                         /* a byte of the payload: the checksum no longer agrees */
    blank();
    expect("a damaged file is refused", !rr_cps1_save_begin() && chip.data[3] == 0xff);
    chip.data[9] = 0x01; chip.changed = 1;
    rr_cps1_save_frame();
    expect("and is not written over", !rr_cps1_save_close());
    blank();
    expect("it is still the damaged one", !rr_cps1_save_begin());

    remove_file();
    blank();
    rr_cps1_save_begin(); chip.data[1] = 0x11; chip.changed = 1; rr_cps1_save_frame(); rr_cps1_save_close();
    edit_file(30, 'X');                           /* the set identity inside the header */
    blank();
    expect("a file written for another set is refused", !rr_cps1_save_begin() && chip.data[1] == 0xff);
    /* side effects off (a silent frame, a guest): the change flag is taken, no file is asked for, and the change is not asked later either */
    remove_file();
    blank();
    rr_cps1_save_begin();
    rr_cps1_save_side_effects(0);
    chip.data[2] = 0x33; chip.changed = 1;
    rr_cps1_save_frame();
    expect("a frame without side effects takes the change flag", chip.changed == 0);
    expect("and asks for no file", !file_appears_within(1700));
    rr_cps1_save_side_effects(1);
    rr_cps1_save_frame();
    expect("a later frame with nothing changed asks for none either", !file_appears_within(1500));
    chip.data[2] = 0x34; chip.changed = 1;
    rr_cps1_save_frame();
    expect("a change with side effects on is written", file_appears_within(4000));
    expect("closing after it is fine", rr_cps1_save_close());

    /* a multiplayer guest (hostkit.h side_effects off for the whole session): it starts on its own file, is handed the host's image in memory
     * (what cps1_eeprom_load does), asks for no file whatever the game writes, and closing writes none: its own file is as it was */
    blank();
    expect("the player's file exists", rr_cps1_save_begin() && chip.data[2] == 0x34);
    rr_cps1_save_close();
    blank();
    expect("a guest starts as alone", rr_cps1_save_begin() && chip.data[2] == 0x34);
    rr_cps1_save_side_effects(0);
    memset(chip.data, 0x5a, CPS1_EEPROM_BYTES); chip.changed = 0;     /* the host's image, put before the boot digest */
    chip.data[9] = 0x11; chip.changed = 1;                              /* the game writes in the match */
    rr_cps1_save_frame();
    sleep_ms(1700);                                                     /* longer than the pause before a write */
    expect("closing a guest is fine", rr_cps1_save_close());
    rr_cps1_save_side_effects(1);
    blank();
    expect("its own file is as it was", rr_cps1_save_begin() && chip.data[2] == 0x34 && chip.data[9] == 0xff);
    rr_cps1_save_close();

    remove_file();
    printf("{\"passed\":%u,\"failed\":%u}\n", passed, failed);
    return failed ? 1 : 0;
}
