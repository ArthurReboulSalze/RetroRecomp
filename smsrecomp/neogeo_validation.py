"""Bounded MVS boot/demo/coin/start inputs and separate CPU coverage gates.

The route is an authored controller script. Agreement within the Geolith
hardware family is integration evidence, not independent physical fidelity.
"""
FIELDS=('frames','m1_instructions','sm1_instructions','z80_hash','hardware_hash','state_bytes',
    'bios_instructions','cart_instructions','ram_instructions','pc','image_hash','pcm_hash',
    'pcm_samples','nonzero_samples','peak','clipped_samples','cpu_hash','ram_hash','reached_pc','rtc_seeded','rtc_seed')
ROUTES={
  'attract':(3600,'0 00 00 0 0\n'),
  'play':(5400,'0 00 00 0 0\n2400 00 00 1 0\n2408 00 00 0 0\n2460 00 00 0 1\n2468 00 00 0 0\n'
          '2700 10 00 0 0\n2710 00 00 0 0\n3000 18 00 0 0\n3120 14 00 0 0\n3240 18 00 0 0\n'
          '3360 10 00 0 0\n3600 14 00 0 0\n4200 18 00 0 0\n4800 00 00 0 0\n')}
# Authored late route: continue through game-over/card prompts using A presses.
# It exposed additional BIOS/cartridge entries and an actual memory-card write.
ROUTES['card-save']=(13800,ROUTES['play'][1]+''.join(
    f'{f} 10 00 0 0\n{f+8} 00 00 0 0\n' for f in range(5400,13500,180)))


def action_route(play_script):
    """Exercise all four joystick buttons, not only fire and jump.

    These are controller inputs, not game-specific memory or code patches.
    Separate held-out paths remain necessary for actual gameplay coverage.
    """
    events={int(line.split()[0]):tuple(int(v,16) for v in line.split()[1:])
            for line in play_script.splitlines() if int(line.split()[0])<4000}
    for frame in range(4000,7200,24):
        step=(frame-4000)//24
        events[frame]=((1,2,4,8)[step%4]|(16,32,64,128)[(step//4)%4],0,0,0)
    return (7200,''.join(f'{f} {a:02x} {b:02x} {c:x} {d:x}\n'
        for f,(a,b,c,d) in sorted(events.items())))


def qualification_routes(set_name: str = '') -> dict:
    """Controller scenarios only, never guest-memory or game-code patches.

    The NAM receipt keeps its historical route. Other cartridges use a common
    MVS boot/start scenario with explicit genre input exploration. Every result
    is still validated against its own exact inputs and reference execution.
    """
    if set_name=='nam1975':return {**ROUTES,'actions':action_route(ROUTES['play'][1])}
    events={0:(0,0,0,0),2400:(0,0,1,0),2408:(0,0,0,0),2460:(0,0,0,1),2468:(0,0,0,0)}
    def pulse(frame,value,player=0):
        pads=[0,0];pads[player]=value;events[frame]=(*pads,0,0);events[frame+8]=(0,0,0,0)
    # Confirm instructions, character/car selection and, for Neo Drift Out,
    # each of the three name-entry characters with separate presses.
    for f in range(2700,3900,120):pulse(f,16)
    for f in range(4000,7000,120):
        if set_name=='neodrift':mask=16|(4 if (f//240)%2 else 8)
        elif set_name in ('samsho2','fatfury2','kof98','kof99','garou','kof2000','kof2003','svc','kof2002','lastbld2'):mask=(1 if (f//360)%3==0 else 4 if (f//360)%3==1 else 8)|(16<<((f//120)%4))
        else:mask=(4 if (f//240)%2 else 8)|16|(32 if set_name in ('mslug','mslug3','mslugx','mslug5') and (f//120)%3==0 else 0)
        events[f]=(mask,0,0,0);events[f+72]=(0,0,0,0)
    def text(rows):return ''.join(f'{f} {p1:02x} {p2:02x} {coin:x} {start:x}\n' for f,(p1,p2,coin,start) in sorted(rows.items()))
    routes={'attract':ROUTES['attract'],'play':(7200,text(events))}
    # Metal Slug's autonomous demo reaches additional indirect routines after
    # the first minute, beyond the short player-controlled opening sequence.
    if set_name=='mslug':routes['long-attract']=(5400,ROUTES['attract'][1])
    if set_name in ('fatfury2','kof98','kof99','mslug3','garou','kof2000','mslugx','mslug5','kof2003','svc'):routes['long-attract']=(9000,ROUTES['attract'][1])
    if set_name in ('mslug','pbobblen','samsho2','fatfury2','kof98','kof99','mslug3','garou','kof2000','mslugx','mslug5','kof2003','svc',
                    'turfmast','blazstar','pulstar','shocktro','bstars2','magdrop3','spinmast','viewpoin','kof2002','lastbld2'):
        two={0:(0,0,0,0),2400:(0,0,3,0),2408:(0,0,0,0),2460:(0,0,0,5),2468:(0,0,0,0)}
        for f in range(2700,3900,120):two[f]=(16,16,0,0);two[f+8]=(0,0,0,0)
        for f in range(4000,6200,120):
            two[f]=(8|16,4|32,0,0);two[f+60]=(0,0,0,0)
        routes['two-player']=(6600,text(two))
    routes['actions']=action_route(routes['play'][1])
    return routes


def extended_routes(set_name: str, plans: dict | None = None, *, aes: bool = False) -> dict:
    """Add developer controller routes; the mandatory product checks stay on.

    The bounded batch qualifier passes these explicitly. They are not enabled
    for every end-user conversion, and cannot replace the standard routes.
    """
    routes=qualification_routes(set_name)
    if aes:
        routes['aes-attract'] = ROUTES['attract']
        routes['aes-play'] = routes['play']
    import re
    for name,value in (plans or {}).get(set_name,{}).items():
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',name) or name in routes:
            raise ValueError('Extra Neo Geo route cannot replace a mandatory route.')
        frames,script=value
        if not isinstance(frames,int) or not 1<=frames<=1000000 or not isinstance(script,str):
            raise ValueError('Invalid extra Neo Geo frame/input limit.')
        previous=-1
        for line in script.splitlines():
            fields=line.split()
            if len(fields)!=5:raise ValueError('Invalid Neo Geo controller row.')
            frame=int(fields[0]);p1,p2,coin,start=(int(s,16) for s in fields[1:])
            if frame<=previous or frame>=frames or min(frame,p1,p2,coin,start)<0 or max(p1,p2)>255 or coin>3 or start>15:
                raise ValueError('Extra Neo Geo routes accept ordered controller inputs only.')
            previous=frame
        if previous<0:raise ValueError('Empty Neo Geo controller route.')
        routes[name]=(frames,script)
    return routes

def compare(native,reference,*,require_native=True):
    differences=[field for field in FIELDS if native[field]!=reference[field]]
    for field in ('reached_physical','extended_cpu_hash','extended_hardware_hash','cpu_slice_clocks'):
        if field in native and field in reference and native[field]!=reference[field]:differences.append(field)
    for cpu in ('68000','z80'):
        if native['native_'+cpu]+native['interpreted_'+cpu]!=reference['native_'+cpu]+reference['interpreted_'+cpu]:
            differences.append(cpu+'_instruction_total')
        if require_native and (native['interpreted_'+cpu] or not native['native_'+cpu]):
            differences.append(cpu+'_native_coverage')
    if differences:raise RuntimeError('Neo Geo mismatch: '+', '.join(differences))
    return differences
