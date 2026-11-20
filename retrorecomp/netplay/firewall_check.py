"""Does Windows' firewall let a host's room receive? Read-only: the converter never adds, changes or removes a rule.

A host's room listens on one port (TCP for the room, UDP for the frames) in its worker process. When Windows' firewall
blocks new inbound connections and no rule allows that program on that port, every guest gets « no answer » and the host
sees nothing at all. Players (and their own firewall tools, which often hide Windows' « allow access? » prompt) then turn
the whole firewall off. This module reads the firewall's state once per room, so the host is told plainly instead.

    state, detail = check(program, address, port, internet)     # 'open', 'blocked' or 'unknown'

* Windows only (`unknown` elsewhere, or when the firewall cannot be read). It runs one PowerShell process that reads the
  firewall policy through its COM object (HNetCfg.FwPolicy2: read access, no administrator needed) and the network profile
  of the interface holding `address`; `evaluate` decides from that record, so a test can give its own.
* `open`: the firewall is off for that profile, it allows new inbound connections by default, or an enabled Allow rule names
  this program (or no program) for this port, TCP and UDP. An Internet room also needs that rule to accept any remote address
  (a rule limited to the local subnet lets LAN guests in, not Internet ones).
* `blocked`: anything else, including « block all incoming connections » and a Block rule for this program. `detail` says
  which part (tcp, udp, remote) in words for a log.
* Rules without a program and without a port (Windows' own, tied to services or packages) are not taken as letting the room
  in: they say nothing about this program.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import subprocess
import sys

OPEN, BLOCKED, UNKNOWN = 'open', 'blocked', 'unknown'
TIMEOUT = 12.0                      # seconds for the PowerShell read (about 1 s on the owner's PC with 400 inbound rules)
TCP, UDP, ANY = 6, 17, 256
DOMAIN, PRIVATE, PUBLIC = 1, 2, 4
CATEGORY_BITS = {0: PUBLIC, 1: PRIVATE, 2: DOMAIN}     # Get-NetConnectionProfile's NetworkCategory

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$p = New-Object -ComObject HNetCfg.FwPolicy2
$current = [int]$p.CurrentProfileTypes
$category = $null
try {
  $ip = Get-NetIPAddress -IPAddress '__ADDRESS__' -ErrorAction Stop | Select-Object -First 1
  $category = [int](Get-NetConnectionProfile -InterfaceIndex $ip.InterfaceIndex -ErrorAction Stop | Select-Object -First 1).NetworkCategory
} catch { }
$profiles = @()
foreach ($bit in 1, 2, 4) {
  $profiles += [pscustomobject]@{ bit = $bit; enabled = [bool]$p.FirewallEnabled($bit); blockall = [bool]$p.BlockAllInboundTraffic($bit);
                                  inbound = [int]$p.DefaultInboundAction($bit) }
}
$rules = @()
foreach ($r in $p.Rules) {
  if ($r.Direction -ne 1 -or -not $r.Enabled) { continue }
  if ($r.Protocol -ne 6 -and $r.Protocol -ne 17 -and $r.Protocol -ne 256) { continue }
  $rules += [pscustomobject]@{ app = $r.ApplicationName; action = [int]$r.Action; protocol = [int]$r.Protocol; ports = $r.LocalPorts;
                               remote = $r.RemoteAddresses; profiles = [int]$r.Profiles }
}
[pscustomobject]@{ current = $current; category = $category; profiles = $profiles; rules = $rules } | ConvertTo-Json -Depth 4 -Compress
"""


def _same_program(rule_app: str | None, program: str) -> bool:
    if not rule_app:
        return False
    expanded = os.path.expandvars(rule_app)
    return os.path.normcase(os.path.normpath(expanded)) == os.path.normcase(os.path.normpath(program))


def _port_in(ports, port: int) -> bool:
    """`LocalPorts` of a rule: '*', '24611', '24000-25000', comma lists; None or '' means any port."""
    if ports in (None, '', '*'):
        return True
    for part in str(ports).split(','):
        part = part.strip()
        if part == '*':
            return True
        if '-' in part:
            low, _, high = part.partition('-')
            if low.strip().isdigit() and high.strip().isdigit() and int(low) <= port <= int(high):
                return True
        elif part.isdigit() and int(part) == port:
            return True
    return False


def _any_remote(remote) -> bool:
    return remote in (None, '', '*')


def evaluate(record: dict, program: str, port: int, internet: bool) -> tuple[str, str]:
    """The verdict of one read of the firewall (`SCRIPT`'s record) for a room of `program` on `port`."""
    try:
        bit = CATEGORY_BITS.get(record.get('category'))
        if bit is None:                          # the interface's profile was not found: every active profile must let it in
            current = int(record.get('current') or 0)
            bits = [value for value in (DOMAIN, PRIVATE, PUBLIC) if current & value] or [PRIVATE]
        else:
            bits = [bit]
        profiles = {int(item['bit']): item for item in record.get('profiles') or []}
        rules = record.get('rules') or []
        if isinstance(rules, dict):              # ConvertTo-Json writes a list of one as the object itself
            rules = [rules]
        reasons = []
        for profile in bits:
            state = profiles.get(profile)
            if state is None:
                return UNKNOWN, 'the firewall profile could not be read'
            if not state.get('enabled'):
                continue
            if state.get('blockall'):
                reasons.append('every incoming connection is blocked')
                continue
            if int(state.get('inbound', 0)) == 1:
                continue
            for protocol, word in ((TCP, 'tcp'), (UDP, 'udp')):
                allowed = blocked = remote_only_local = False
                for rule in rules:
                    if not int(rule.get('profiles') or 0) & profile:
                        continue
                    if int(rule.get('protocol') or 0) not in (protocol, ANY):
                        continue
                    if not _port_in(rule.get('ports'), port):
                        continue
                    app = rule.get('app')
                    if app:
                        if not _same_program(app, program):
                            continue
                    elif rule.get('ports') in (None, '', '*'):
                        continue                 # no program and no port: Windows' own rules, nothing about this room
                    if int(rule.get('action', 1)) == 0:
                        blocked = True
                    elif internet and not _any_remote(rule.get('remote')):
                        remote_only_local = True
                    else:
                        allowed = True
                if blocked:
                    reasons.append(f'a rule blocks {word}')
                elif not allowed:
                    reasons.append(f'{word} from the Internet is limited to the local network' if remote_only_local
                                   else f'no rule lets this program receive {word} on port {port}')
        return (BLOCKED, '; '.join(dict.fromkeys(reasons))) if reasons else (OPEN, '')
    except (TypeError, ValueError, KeyError, AttributeError):
        return UNKNOWN, 'the firewall record is not what it should be'


def read(address: str, timeout: float = TIMEOUT) -> dict | None:
    """The firewall's record on Windows (one hidden PowerShell process), or None."""
    if sys.platform != 'win32':
        return None
    try:
        address = str(ipaddress.ip_address(address.strip()))
    except (ValueError, AttributeError):
        address = '0.0.0.0'
    script = SCRIPT.replace('__ADDRESS__', address)
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    try:
        done = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                               '-EncodedCommand', encoded], capture_output=True, timeout=timeout,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    try:
        record = json.loads(done.stdout.decode('utf-8', errors='replace').strip() or 'null')
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def check(program: str, address: str, port: int, internet: bool, reader=read) -> tuple[str, str]:
    """Whether a room of `program` bound on `address`:`port` can be reached through Windows' firewall."""
    record = reader(address)
    if record is None:
        return UNKNOWN, 'the firewall could not be read'
    return evaluate(record, program, int(port), bool(internet))
