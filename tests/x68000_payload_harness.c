/* Original Retro-Recomp harness, MIT. Runs the X68000 host's real payload.c (the private game data preparation)
 * against a folder given on the command line. The resources and the payload table come from stubs written by
 * tests/test_x68000_payload.py: no disk image, no firmware, no ROM. */
#include "payload.h"
#include <stdio.h>

int main(int argc, char **argv) {
    char directory[8192];
    if (argc != 2) return 2;
    if (!rr_x68k_payload_prepare(argv[1], directory, sizeof(directory))) {
        puts("PREPARE-FAILED");
        return 1;
    }
    printf("DIRECTORY %s\n", directory);
    rr_x68k_payload_release();
    return 0;
}
