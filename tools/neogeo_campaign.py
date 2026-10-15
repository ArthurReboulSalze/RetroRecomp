"""Finite MVS qualification: local copies, three batches of eight, six long routes.

No ROM is supplied here. --prepare copies explicitly selected user archives;
all output is local and source shares are read-only. No publication is done.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
SETS=('nam1975','mslug','pbobblen','samsho2','neodrift','fatfury2','kof98','kof99',
      'mslug3','mslugx','mslug5','kof2003','garou','kof2000','turfmast','blazstar',
      'pulstar','shocktro','bstars2','magdrop3','spinmast','viewpoin','kof2002','lastbld2')
LONG=('nam1975','mslug','pbobblen','samsho2','turfmast','blazstar')


def long_route(name,frames=54000):
    from smsrecomp.neogeo_validation import qualification_routes
    events={}
    for line in qualification_routes(name)['play'][1].splitlines():
        f,*v=line.split();events[int(f)]=tuple(int(x,16) for x in v)
    # Controller actions only. Credits/start permit game-over/continue routes;
    # no state injection, lives modification or guest-memory writes.
    for f in range(4000,frames-30,30):
        step=(f-4000)//30
        if name=='mslug':p1=8|(16 if step%10<8 else 0)|(32 if step%8 in (0,1) else 0)|(64 if step%47==0 else 0)
        elif name=='nam1975':p1=(8 if step%24<16 else 4)|(16 if step%4<3 else 0)|(32 if step%9<2 else 0)
        elif name=='pbobblen':p1=(4 if step%12<6 else 8)|(16 if step%4==0 else 0)
        elif name=='samsho2':p1=(8 if step%17<12 else 4 if step%17<15 else 1)|(16<<(step%4))
        elif name=='turfmast':p1=(4 if step%30==25 else 8 if step%30==27 else 0)|(16 if step%7==0 else 0)
        else:p1=(16 if step%10<8 else 0)|(8 if step%100<35 else 4 if step%100<70 else 1)|(32 if step%19==0 else 0)
        events[f]=(p1,0,0,0)
        if (f-4000)%600==0:
            events[f]=(p1,0,1,0);events[f+8]=(p1,0,0,0)
            events[f+15]=(0,0,0,1);events[f+23]=(p1,0,0,0)
    text=''.join(f'{f} {a:02x} {b:02x} {c:x} {d:x}\n' for f,(a,b,c,d) in sorted(events.items()))
    return (frames,text)


def prepare(root,source):
    from smsrecomp.batch import identify
    inputs=root/'inputs';inputs.mkdir(parents=True,exist_ok=True)
    snapshot=root/'base-knowledge.json.gz'
    if not snapshot.exists():shutil.copy2(ROOT/'assets/compilation-knowledge.json.gz',snapshot)
    rows=[]
    for name in (*SETS,'neogeo'):
        original=source/(name+'.zip');local=inputs/('bios.zip' if name=='neogeo' else name+'.zip')
        digest=hashlib.sha256(original.read_bytes()).hexdigest()
        if not local.exists():shutil.copy2(original,local)
        if hashlib.sha256(local.read_bytes()).hexdigest()!=digest:raise ValueError('Input copy differs: '+name)
        item=identify(local) if name!='neogeo' else None
        if item and (item.error or item.system!='ng'):raise ValueError(str(item))
        row={'set':name,'source':str(original),'local':str(local),'sha256':digest,'bytes':local.stat().st_size}
        if item:row.update(title=item.title,identity=item.sha256)
        rows.append(row);print(json.dumps(row),flush=True)
    (root/'inputs.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')


def batch(root,number,retry=None):
    from smsrecomp.batch import identify,convert_batch
    names=tuple(retry) if retry else SETS if number==0 else SETS[(number-1)*8:number*8]
    assert names and (len(names)<=8 or number==0) and all(n in SETS for n in names)
    plans={name:{'sustained-play':long_route(name)} for name in LONG}
    (root/'controller-plans.json').write_text(json.dumps(plans,indent=2),encoding='utf-8')
    items=[identify(root/'inputs'/(name+'.zip')) for name in names]
    result=convert_batch(items,root/'Games',jobs=8,ng_bios=str(root/'inputs/bios.zip'),
        ng_qualification_routes=plans,use_cover=True,online_cover=True,boxart_dir=root/'online-only',
        emit=lambda text:print(text,flush=True))
    output=root/(f'batch-{number}-result.json' if not retry else 'retry-result.json')
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'succeeded':result['succeeded'],'failed':result['failed']}),flush=True)
    if result['succeeded']!=len(items):raise SystemExit(2)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepare',type=Path)
    p.add_argument('--batch',type=int,choices=(0,1,2,3),help='0: queue only the finite 24, always at most eight active')
    p.add_argument('--retry',nargs='+')
    args=p.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=True)
    if args.prepare:prepare(root,args.prepare)
    if args.batch is not None or args.retry:batch(root,args.batch if args.batch is not None else 1,args.retry)


if __name__=='__main__':main()
