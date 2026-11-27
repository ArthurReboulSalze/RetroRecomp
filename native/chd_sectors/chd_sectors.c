/* The converter's CHD reader (Retro-Recomp's own code, MIT): a CHD's hunks, decoded by libchdr (BSD-3-Clause), served to the
 * converter over a pipe. Nothing of it goes into a game: the converter uses it to hash a disc held in a CHD and to write its sectors
 * into a game's disc pack (retrorecomp/chd_native.py), so that a CHD and the CUE/BIN set it was made from give the same game.
 *
 *     chd_sectors <file.chd>
 *
 * On start it writes one header line, then every metadata record of a CD track as one line, then an empty line:
 *     RRCHD 1 <hunk bytes> <total hunks> <unit bytes> <logical bytes>
 *     CHT2 TRACK:1 TYPE:MODE2_RAW SUBTYPE:NONE FRAMES:... (the record's text, as libchdr returns it)
 * Then it reads requests on its input, each a little-endian 32-bit hunk number, and answers each with one status byte (0: the
 * hunk follows, `hunk bytes` long; 1: the hunk could not be read, nothing follows). 0xFFFFFFFF or the end of the input ends it.
 * A CHD that cannot be opened ends it at once with the reason on the error output and exit status 2. Every hunk is checked by
 * libchdr against the CRC its map holds (CHDR_VERIFY_BLOCK_CRC, the library's default). */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <libchdr/chd.h>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static int write_all(const void *data, size_t size)
{
    return fwrite(data, 1, size, stdout) == size;
}

static void metadata(chd_file *chd, uint32_t tag, const char *name)
{
    char text[512];
    for (uint32_t index = 0; index < 256; ++index) {
        uint32_t length = 0, result_tag = 0;
        uint8_t flags = 0;
        memset(text, 0, sizeof(text));
        if (chd_get_metadata(chd, tag, index, text, sizeof(text) - 1, &length, &result_tag, &flags) != CHDERR_NONE)
            break;
        for (char *p = text; *p; ++p)
            if (*p == '\n' || *p == '\r')
                *p = ' ';
        printf("%s %s\n", name, text);
    }
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: chd_sectors <file.chd>\n");
        return 2;
    }
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    chd_file *chd = NULL;
    chd_error error = chd_open(argv[1], CHD_OPEN_READ, NULL, &chd);
    if (error != CHDERR_NONE) {
        fprintf(stderr, "%s\n", chd_error_string(error));
        return 2;
    }
    const chd_header *header = chd_get_header(chd);
    printf("RRCHD 1 %u %u %u %llu\n", header->hunkbytes, header->totalhunks, header->unitbytes,
           (unsigned long long)header->logicalbytes);
    metadata(chd, CDROM_TRACK_METADATA2_TAG, "CHT2");
    metadata(chd, CDROM_TRACK_METADATA_TAG, "CHTR");
    metadata(chd, CDROM_OLD_METADATA_TAG, "CHCD");
    metadata(chd, GDROM_TRACK_METADATA_TAG, "CHGD");
    metadata(chd, GDROM_OLD_METADATA_TAG, "CHGT");
    printf("\n");
    fflush(stdout);

    uint8_t *hunk = malloc(header->hunkbytes);
    if (!hunk) {
        chd_close(chd);
        return 2;
    }
    uint8_t request[4];
    while (fread(request, 1, 4, stdin) == 4) {
        const uint32_t number = (uint32_t)request[0] | (uint32_t)request[1] << 8 | (uint32_t)request[2] << 16 |
                                (uint32_t)request[3] << 24;
        if (number == 0xFFFFFFFFu)
            break;
        const uint8_t ok = number < header->totalhunks && chd_read(chd, number, hunk) == CHDERR_NONE ? 0 : 1;
        if (!write_all(&ok, 1) || (ok == 0 && !write_all(hunk, header->hunkbytes)))
            break;
        fflush(stdout);
    }
    free(hunk);
    chd_close(chd);
    return 0;
}
