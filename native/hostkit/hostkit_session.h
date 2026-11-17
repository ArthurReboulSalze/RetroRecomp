/* A multiplayer session of the host kit (multiplayer stage 0, .build/multiplayer/HOOKS.md).
 *
 * A game is in a session only when the converter's netplay worker started it with RETRORECOMP_NETPLAY_PIPE="<in>,<out>": two
 * anonymous pipe handles (Windows HANDLE values, POSIX file descriptors) the game inherited. Without it nothing below runs and
 * the game plays alone exactly as before: the kit's only cost is the test of rrhk_session_on, once per frame.
 *
 * In a session the game opens no socket and decides nothing. Once per frame it reports its local pad (LOCAL) and executes the
 * worker's commands: run a frame with the given port words (live, or silent: no picture, no sound), save or load a snapshot of
 * its own ring (memory only, never sent), give a digest, pause, show a notice, stop. Snapshots never leave the process.
 *
 * Messages, both ways: u16 type, u16 payload length, payload (little-endian, at most RRHK_SESSION_MAX_PAYLOAD bytes). A message
 * that breaks these rules stops the session ("connection to Retro-Recomp lost"); the game never blocks on the pipe.
 *
 * Original Retro-Recomp code, MIT. */
#ifndef RR_HOSTKIT_SESSION_H
#define RR_HOSTKIT_SESSION_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Raised whenever a message, a field or the meaning of one changes. The lobby also compares the host stamp. */
#define RRHK_SESSION_ABI 2           /* 2: restart for everyone (RRHK_SYS_RESTART, RRHK_RUN_RESET) */
#define RRHK_SESSION_MAX_PAYLOAD 4096
#define RRHK_SESSION_MAX_RING 64
#define RRHK_SESSION_ENV "RETRORECOMP_NETPLAY_PIPE"

enum {
    /* game -> worker */
    RRHK_MSG_HELLO = 1,      /* u16 abi, u8 players, u8 caps (RRHK_CAP_*), u32 snap_bound, u32 frame_rate_millihertz,
                              * u8 name length, ini section name (ASCII) */
    RRHK_MSG_LOCAL = 2,      /* u32 frame about to run, u16 word (player 1's controls of this PC), u16 system bits */
    RRHK_MSG_DONE = 3,       /* u32 frame just run live, u32 cost in microseconds */
    RRHK_MSG_DIGEST_OF = 4,  /* u32 last frame run, u64 digest */
    RRHK_MSG_REFUSED = 5,    /* u16 code (RRHK_REFUSED_*), u8 length, text (an option key) */
    RRHK_MSG_EXIT = 6,       /* u16 reason (RRHK_EXIT_*) */
    /* worker -> game */
    RRHK_MSG_SETUP = 32,     /* u8 local seat, u8 ports, u8 ring depth, u8 flags (RRHK_SETUP_*), u16 length, options
                              * "key=value" lines separated by '\n' (ASCII) */
    RRHK_MSG_RUN = 33,       /* u32 frame, u8 flags (RRHK_RUN_*), u8 count, count x u16 port words */
    RRHK_MSG_SAVE = 34,      /* u32 frame: snapshot of the state before that frame runs, into the ring */
    RRHK_MSG_LOAD = 35,      /* u32 frame: back to the snapshot taken before that frame */
    RRHK_MSG_DIGEST = 36,    /* (empty): answer DIGEST_OF for the state now */
    RRHK_MSG_PAUSE = 37,     /* u8 on, u8 length, name of who paused (UTF-8, already cleaned by the worker) */
    RRHK_MSG_NOTICE = 38,    /* u16 code (RRHK_NOTICE_*), u8 length, argument (a player's name) */
    RRHK_MSG_PACE = 39,      /* i32 parts per million added to the frame period (time sync), within +-20000 */
    RRHK_MSG_STOP = 40,      /* u16 reason (RRHK_STOP_*) */
};

enum { RRHK_CAP_SNAPSHOT = 1, RRHK_CAP_DIGEST = 2, RRHK_CAP_POINTER = 4, RRHK_CAP_AXES = 8, RRHK_CAP_KEYBOARD = 16,
       RRHK_CAP_DRIVEN = 32 };
enum { RRHK_SETUP_GUEST = 1 };          /* a guest never writes its cartridge save */
enum { RRHK_RUN_SILENT = 1,            /* re-simulation: no picture, no sound, no side effects */
       RRHK_RUN_RESET = 2 };           /* the machine restarts before this frame runs (live or silent): the host asked it */
enum { RRHK_SYS_PAUSE = 1,             /* the player asked for a pause (the Pause key, a menu) */
       RRHK_SYS_RESTART = 2 };         /* the host asked to restart (Shift+F1, the pad combination): in one frame's LOCALs */
enum { RRHK_REFUSED_OPTION = 1, RRHK_REFUSED_SNAPSHOT = 2, RRHK_REFUSED_COMMAND = 3 };
enum { RRHK_EXIT_CLOSED = 1, RRHK_EXIT_LOST = 2, RRHK_EXIT_STOPPED = 3, RRHK_EXIT_FAILED = 4 };
enum { RRHK_NOTICE_WAITING = 1, RRHK_NOTICE_RESUMED = 2, RRHK_NOTICE_LEFT = 3 };
enum { RRHK_STOP_HOST_CLOSED = 1, RRHK_STOP_DESYNC = 2, RRHK_STOP_ENDED = 3,
       RRHK_STOP_BOOT_MISMATCH = 4 };   /* this game does not start from the host's state: the launch is refused */

#endif
