# Multiplayer

Play a converted game with friends: one PC **hosts** a room, the others **join** it with an invitation, and every PC runs
its own copy of the same export. Only the controllers travel between the PCs, never the game. Every game checks
continuously that it stays identical to the host's copy, and a match stops with a reason rather than letting two screens
drift apart. Physical latency (from a button to the picture) is not measured. The input delay below is counted in frames,
which is not the same measure.

## Hosting and joining

- **Host:** in the converter, open **Multiplayer** and choose **Host**, or right-click a game in **Compiled Games** and
  choose **Host a multiplayer game…**. Pick the game, open the room, then **Copy** the invitation and send it to your
  friends. The invitation holds the room's secret: share it only with the players.
- **Join:** **Multiplayer**, then **Join**, then paste the invitation. The room checks that you have the same game in the same
  version (the **Game** column). If yours differs, it names the reason (another converter version, another option, a
  missing firmware).
- When your game matches, press the big **I'm ready** button. The host clicks **Launch**, and the game opens on every PC.
- The lobby has a chat, and the room shows each player's link while a match runs.
- The host must let the room's port (24611, TCP and UDP) in through its firewall. A guest only needs to connect out. The
  installer offers an optional rule for it (unticked by default); when Windows' firewall would block the guests anyway, the
  host's room says so plainly.

## How a match plays

| | |
|---|---|
| **Controls** | Three modes on every machine: **One controller per player**, **Everyone** (shared controls, all at once) and **Turns** (shared controls, one player at a time). One controller per player puts each player on the machine's ports, up to four players. On the handhelds (Game Boy, Game Gear, Game Boy Advance) it is their **link cable** (below), said under the choice; there is no separate « link » mode. |
| **Turns** | The player who has the controller passes it with F2's **Pass the controller** tile; the host gives it to anyone (**Give the controller to…**) and switches between Everyone and Turns, in the game or in the Multiplayer window. A badge shows who has it (it can be hidden in F2's options). |
| **Link cable** | On the Game Boy, the Game Gear and the Game Boy Advance, **One controller per player** plays over the link cable: each player plays their own console, linked as by a real cable. Every PC runs every console, so only the controllers travel, and each PC shows and plays the sound of its own player's console (F2 says « You are P2 »). Two consoles. Every console starts from the host's save, and only the host's console's save is written back at the end. On the Game Boy Advance every game links: the code only the cable runs is interpreted when the game's cable code has not been reviewed (counted and written in the game's log, never a stop of the match). Single-Pak (multiboot) link modes, where one cartridge sends its game to consoles that have none (Bomberman Tournament's Group mode, Mario Kart's one-cartridge race), are not supported yet. |
| **Smooth mode (rollback)** | The game does not wait for the other players' buttons. It guesses them and corrects itself at once when the true ones arrive, so a far player does not slow the game down. Up to five frames are guessed; a slower link adds input delay instead. |
| **Delay mode** | Every PC waits for every player's buttons, one or two frames on a local network. It is used for the PlayStation, the Nintendo 64 and the Game Boy Advance, and for any game that cannot rewind. |
| **Pause** | The pause and the menus (F1, F2) pause the match for everyone. The player who paused, or the host, resumes it. |
| **Restart** | Shift+F1, the pad's Restart combination or F2's **Restart the game** tile restarts the game for everyone, from the host only. |
| **Quick save and load** | F8 and F9 (or the pad's combinations) save and load the match for everyone, from the host only. That save lives in memory for the current match: your own quick states are never read or written. |
| **The game's own saves** | Battery saves, memory cards, EEPROMs and save files are the host's for the match: the guests play on a copy in memory and never write their own. |
| **The host's settings** | Settings that change how the game runs (PGXP and the CPU resolution on the PlayStation, the CPU speed of the Amiga, the Neo Geo's clock and system, the sprite limit of the NES and Master System, the DIP switches of the CPS boards…) are the host's for everyone: the guests see them greyed. The host can change one during the match: a question asks first, then the game starts again for everyone with the new setting. Settings that only change the picture stay your own. |
| **The computer's keyboard** | On the Amiga, Atari ST, X68000 and MSX, the host types for everyone: Ctrl+Alt+K hands the host's keyboard to the computer, and every PC's computer gets the same keys at the same frame. The guests stay on their controllers. The function keys stay the converter's in a match. |
| **Chat** | Y on the keyboard, or R3 + Select on the gamepad, opens the in-game chat, with ready-made phrases or free text. |
| **Clock** | Machines with a real-time clock start on the same date on every PC. |

Not carried yet: the mouse and light guns, and a guest's keyboard. On the Nintendo 64, restarting is not available during a
match. On the PlayStation, a disc cannot be changed during a match.

## Machines

| Machine | Mode | Players | Notes |
|---|---|---|---|
| NES | smooth | up to 4 | Four Score / NES Satellite games read players 3 and 4 |
| Master System | smooth | 2 | |
| Game Gear | smooth | shared, or 2 by link cable | |
| Mega Drive | smooth | up to 4 | Team Player, EA 4 Way Play and J-Cart, chosen per game from three players on |
| Super Nintendo | smooth | up to 4 | every enhancement chip; Super Multitap games from three players on |
| PC Engine | smooth | up to 4 | the multitap is always plugged for a game built for two or more |
| PC Engine CD | smooth | the game's own count (2 today) | the System Card, the drive and the backup memory travel with the snapshot; the backup memory is the session's save; the room refuses another System Card (« firmware ») |
| Neo Geo | smooth | 2 | |
| CPS-1, CPS-1.5, CPS-2 | smooth | up to 4 | |
| MSX, MSX2, MSX2+ | smooth | 2 | the host types on the keyboard |
| SG-1000 | smooth | 2 | in development, developer only; Pause is a bit of each seat's word |
| ColecoVision | smooth | 2 | in development, developer only; the keypad's keys travel in the word, both PCs need the same BIOS |
| Game Boy | smooth | shared, or 2 by link cable | |
| Game Boy Advance | delay | shared, or 2 by link cable | the cable on every game (not Single-Pak) |
| Amiga 500 and 1200 | smooth | 2 | the host types on the keyboard |
| Atari ST | smooth | 2 | the host types on the keyboard |
| X68000 | smooth | 2 | the host types on the keyboard |
| PlayStation | delay | 2 | PGXP kept and set by the host |
| Nintendo 64 | delay | up to 4 | analogue sticks carried |
| Adventure (ScummVM) | not offered | | one player |

## Networks

When you host, the room is **Local** (the default, every time) or **Internet** (next section).

- **Local:** the invitation names an address of the local network (10.x, 172.16-31.x, 192.168.x, 169.254.x) or of a **VPN
  between friends** such as Tailscale or ZeroTier (100.64.0.0/10). A VPN also crosses home routers and mobile networks on its
  own: each player installs it and joins the same network, and the host uses its VPN address in the room.
- **Internet:** the host's public address, with a port its box opens or that you open. A relay of our own is not offered:
  when the host cannot be reached, the window says so.

## Playing over the Internet

The owner played over the Internet between two PCs on 19 November 2026, one of them on a phone's connection. That is a play
test: the input delay is still counted in frames, and physical latency is not measured.

- **The key.** The host's room shows a key that starts with `RR2-`. A guest pastes it, as with a local invitation. The
  host can also give the three parts by hand: the address, the port (24611 by default) and the code.
- **Local stays the default**, every time you host or join. Choosing **Internet** shows three warnings, and you confirm
  them before it is on: your public address is in the key you share; your box opens a port while the room is open and
  closes it after; share the key only with people you trust.
- **How the host's address is found**, in this order: your box (UPnP, then NAT-PMP), then your PC's own IPv6 address, then,
  only when both fail and the window says so, retro-recomp.com, which answers with the address it saw. You can always type
  the address yourself.
- **The port.** The host must be reachable on port 24611, TCP and UDP. The box opens it when it agrees. When it refuses,
  you open it by hand in the box ("port forwarding", "NAT/PAT") towards your PC's local address; the window's help gives
  the steps for the usual French boxes, and you remove the rule after playing.
- **When the host cannot be reached** (an address shared with other subscribers, a second router, a phone hotspot), the
  window says so and suggests three ways out: let another player host, open the port in the box, or put the friends on a
  VPN such as Tailscale or ZeroTier. A guest is never affected.
- **Encryption** is the one described in [What is checked](#what-is-checked); the Internet room adds no other.

## What is checked

Everything a room sends is encrypted: each connection agrees a fresh key with an X25519 exchange tied to the invitation's
secret, and every message and every match packet is sealed with ChaCha20-Poly1305 (the `cryptography` package). Someone on
the same network or on the path sees that two PCs talk, not the names, the chat or the buttons, and cannot join without
the invitation.

Every seat folds the inputs it was given into a running digest, and compares a digest of its machine's state with the
host's every second. Before the first frame, the state after setup is compared too: a different save, option or firmware
is refused with its reason. Each machine's rewinding was proven on real games run as two copies with simulated latency
and lost packets, and on two PCs on a home network. The results are in [UPGRADES.md](UPGRADES.md).

## When a game closes by itself

Each PC keeps what happened in the converter's `datas/logs` folder. Nothing in it is ever sent anywhere.

- `room.log`: the room's events, the host's and the guest's, with one line per match saying how it ended: the outcome, the
  game's exit code and the game's own reason line, for example
  « match 5 over: broke (the machine stopped), exit 0 - [host] the link cable stopped: … ».
- `games/`: what each game started by the converter wrote (multiplayer, Compiled Games, the Front-end), one file per
  launch. Each file is cut to its last 64 KB and only the 20 most recent are kept.

Attach the room log and the game's file to a problem report when a match ends on its own.
