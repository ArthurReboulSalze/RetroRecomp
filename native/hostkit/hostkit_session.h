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
#define RRHK_SESSION_ABI 8           /* 2: restart for everyone (RRHK_SYS_RESTART, RRHK_RUN_RESET); 3: the chat (CHAT_OUT, CHAT_SHOW,
                                     * the turn notices, NOTICE_CHAT_SLOW); 4: the host's quick save and load for everyone
                                     * (RRHK_SYS_STATE_*, RRHK_RUN_STATE_*); 5: a driven machine with snapshots takes silent
                                     * RUNs (its guest runs the frame; rollback for every machine); 6: HELLO carries the game's
                                     * run-changing options (RrhkMachine.session_options), the host's go to every seat;
                                     * 7: the sticks travel (LOCAL and RUN carry RRHK_AXES int8 values per player);
                                     * 8: the host's save travels (HELLO's save size, SAVE_OUT, SAVE_IN) */
#define RRHK_SESSION_MAX_PAYLOAD 4096
#define RRHK_SESSION_MAX_RING 64
#define RRHK_SESSION_MAX_OPTIONS 1024
#define RRHK_SESSION_MAX_SAVE (2u * 1024u * 1024u)   /* the largest save image a game gives or takes */
#define RRHK_SESSION_SAVE_CHUNK 4000                 /* the data of one SAVE_OUT / SAVE_IN */
#define RRHK_SESSION_ENV "RETRORECOMP_NETPLAY_PIPE"
/* The clock every seat's machine runs on in a session (RrhkMachine.session_begin): 1 January 2000, 00:00 UTC, so that two PCs
 * whose clocks differ start alike. A clock the host gives would be a change of SETUP (a new ABI). */
#define RRHK_SESSION_CLOCK 946684800ull

enum {
    /* game -> worker */
    RRHK_MSG_HELLO = 1,      /* u16 abi, u8 players, u8 caps (RRHK_CAP_*), u32 snap_bound, u32 frame_rate_millihertz,
                              * u8 name length, the machine's name (console_name, else ini_section; ASCII), u16 options
                              * length, this PC's run-changing options ("key=value" lines, ASCII, at most
                              * RRHK_SESSION_MAX_OPTIONS bytes), u32 the size of this game's save image (0: none) */
    RRHK_MSG_LOCAL = 2,      /* u32 frame about to run, u16 word (player 1's controls of this PC), u16 system bits, then for a
                              * machine with sticks (RRHK_CAP_AXES) RRHK_AXES x i8 (LX, LY, RX, RY: -127..127, the original
                              * pads' precision) */
    RRHK_MSG_DONE = 3,       /* u32 frame just run live, u32 cost in microseconds */
    RRHK_MSG_DIGEST_OF = 4,  /* u32 last frame run, u64 digest */
    RRHK_MSG_REFUSED = 5,    /* u16 code (RRHK_REFUSED_*), u8 length, text (an option key) */
    RRHK_MSG_EXIT = 6,       /* u16 reason (RRHK_EXIT_*) */
    RRHK_MSG_CHAT_OUT = 7,   /* u8 phrase (RRHK_PHRASE_*, 0: free text), u8 length, text: printable ASCII, 1 to
                              * RRHK_CHAT_MAX_TEXT bytes for free text, none with a phrase. The host stamps the name. */
    RRHK_MSG_SAVE_OUT = 8,   /* u32 offset, data (at most RRHK_SESSION_SAVE_CHUNK): the game's save image right after HELLO, in
                              * order, as much as HELLO said; the host's is what every seat plays on */
    /* worker -> game */
    RRHK_MSG_SETUP = 32,     /* u8 local seat, u8 ports, u8 ring depth, u8 flags (RRHK_SETUP_*), u16 length, options
                              * "key=value" lines separated by '\n' (ASCII) */
    RRHK_MSG_RUN = 33,       /* u32 frame, u8 flags (RRHK_RUN_*), u8 count, count x u16 port words, then with RRHK_RUN_AXES
                              * count x RRHK_AXES x i8 sticks */
    RRHK_MSG_SAVE = 34,      /* u32 frame: snapshot of the state before that frame runs, into the ring */
    RRHK_MSG_LOAD = 35,      /* u32 frame: back to the snapshot taken before that frame */
    RRHK_MSG_DIGEST = 36,    /* (empty): answer DIGEST_OF for the state now */
    RRHK_MSG_PAUSE = 37,     /* u8 on, u8 length, name of who paused (UTF-8, already cleaned by the worker) */
    RRHK_MSG_NOTICE = 38,    /* u16 code (RRHK_NOTICE_*), u8 length, argument (a player's name) */
    RRHK_MSG_PACE = 39,      /* i32 parts per million added to the frame period (time sync), within +-20000 */
    RRHK_MSG_STOP = 40,      /* u16 reason (RRHK_STOP_*) */
    RRHK_MSG_CHAT_SHOW = 41, /* u8 phrase (0: free text), u8 name length, name (printable ASCII, at most RRHK_CHAT_MAX_NAME),
                              * u8 text length, text (printable ASCII, 1 to RRHK_CHAT_MAX_TEXT for free text, none with a
                              * phrase). Every line of the room, this player's own included, in the host's order. */
    RRHK_MSG_SAVE_IN = 42,   /* before SETUP, a guest: u32 total, u32 offset, data (at most RRHK_SESSION_SAVE_CHUNK): the host's
                              * save image, which the game plays on in memory for this match (RrhkMachine.session_save_put)
                              * and never writes; total 0: no save */
};

enum { RRHK_CAP_SNAPSHOT = 1, RRHK_CAP_DIGEST = 2, RRHK_CAP_POINTER = 4, RRHK_CAP_AXES = 8, RRHK_CAP_KEYBOARD = 16,
       RRHK_CAP_DRIVEN = 32 };
enum { RRHK_SETUP_GUEST = 1 };          /* a guest never writes its cartridge save */
enum { RRHK_RUN_SILENT = 1,            /* re-simulation: no picture, no sound, no side effects (a driven machine's guest runs it
                                      * and ends it at its next rrhk_frame_done) */
       RRHK_RUN_RESET = 2,             /* the machine restarts before this frame runs (live or silent): the host asked it */
       RRHK_RUN_STATE_SAVE = 4,        /* the match's state is saved before this frame runs (the host's F8, on every seat) */
       RRHK_RUN_STATE_LOAD = 8,        /* the match's state is loaded back before this frame runs (the host's F9). The
                                      * match's state is one slot in memory: never a file, never sent, gone with the match;
                                      * the player's own quick states are not touched. At most one of RESET, STATE_SAVE,
                                      * STATE_LOAD in a RUN. */
       RRHK_RUN_AXES = 16 };           /* the RUN carries every port's sticks after the words */
enum { RRHK_SYS_PAUSE = 1,             /* the player asked for a pause (the Pause key, a menu) */
       RRHK_SYS_RESTART = 2,           /* the host asked to restart (Shift+F1, the pad combination): in one frame's LOCALs */
       RRHK_SYS_STATE_SAVE = 4,        /* the host asked to save the match's state (F8, the pad's Quick save) */
       RRHK_SYS_STATE_LOAD = 8 };      /* the host asked to load it back (F9, the pad's Quick load) */
enum { RRHK_REFUSED_OPTION = 1, RRHK_REFUSED_SNAPSHOT = 2, RRHK_REFUSED_COMMAND = 3 };
enum { RRHK_EXIT_CLOSED = 1, RRHK_EXIT_LOST = 2, RRHK_EXIT_STOPPED = 3, RRHK_EXIT_FAILED = 4 };
enum { RRHK_NOTICE_WAITING = 1, RRHK_NOTICE_RESUMED = 2, RRHK_NOTICE_LEFT = 3,
       RRHK_NOTICE_TURN = 4,            /* shared controls taken in turns: the argument's player has them now */
       RRHK_NOTICE_YOUR_TURN = 5,       /* the same, and it is this player (no argument) */
       RRHK_NOTICE_CHAT_SLOW = 6 };     /* a CHAT_OUT was refused: too many lines (no argument) */
/* The in-game chat: a line is at most 80 characters, a name 16 (the converter transliterates both to ASCII). A phrase is sent
 * as its number, so that every player reads it in the language of their own game. */
#define RRHK_CHAT_MAX_TEXT 80
#define RRHK_CHAT_MAX_NAME 16
enum { RRHK_PHRASE_GG = 1, RRHK_PHRASE_READY = 2, RRHK_PHRASE_AGAIN = 3, RRHK_PHRASE_PAUSE = 4, RRHK_PHRASE_MOMENT = 5,
       RRHK_PHRASE_THANKS = 6, RRHK_PHRASE_COUNT = 6 };
enum { RRHK_STOP_HOST_CLOSED = 1, RRHK_STOP_DESYNC = 2, RRHK_STOP_ENDED = 3,
       RRHK_STOP_BOOT_MISMATCH = 4 };   /* this game does not start from the host's state: the launch is refused */

#endif
