#!/usr/bin/env python3
"""Find confirmed sustainable video bitrates on a fixed degraded-network suite."""
import argparse
import concurrent.futures
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import select
import shutil
import subprocess
import sys
import time
import uuid
from metrics import score
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RATES=[.25,.5,1,2,4,5.5]
PROFILES={'loss_jitter':['delay','40ms','10ms','distribution','normal','loss','1%','rate','5mbit'],
          'burst_loss':['delay','20ms','loss','gemodel','1%','25%','80%','0%','rate','5mbit']}
PROTOCOLS=['tcp','kcp','udp']
def cmd(args):
    return subprocess.run(list(map(str,args)),check=True,text=True,capture_output=True).stdout

def prepare(out,src):
    src=src.resolve();templates={}; records=[]
    for rate in RATES:
        key=f'{rate:g}mbps';folder=out/'media'/key;folder.mkdir(parents=True)
        segments=[]
        for sid in range(5):
            dst=folder/f'{sid}.mkv';bps=str(int(rate*1e6))
            command=['ffmpeg','-v','error','-nostdin','-threads','2','-ss',str(sid),'-i',src,'-t','1','-an','-vf','fps=10,scale=1920:1080','-c:v','libx264','-threads','2','-preset','veryfast','-b:v',bps,'-minrate',bps,'-maxrate',bps,'-bufsize',bps,'-x264-params','nal-hrd=cbr:filler=1:vbv-init=1','-bf','0','-g','10','-pix_fmt','yuv420p',dst]
            cmd(command)
            decoded=cmd(['ffmpeg','-v','error','-xerror','-threads','2','-i',dst,'-f','framemd5','-'])
            assert sum(1 for l in decoded.splitlines() if l and not l.startswith('#'))==10
            (folder/f'{sid}.framemd5').write_text(decoded)
            blob=dst.read_bytes();segments.append({'id':sid,'path':str(dst),'size':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),'frames':10,'target_mbps':rate,'command':list(map(str,command))})
        templates[key]=segments;print(key,'actual encoded rate',sum(s['size'] for s in segments)*8/5e6,flush=True)
    (out/'input.json').write_text(json.dumps({'path':str(src),'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'ffprobe':json.loads(cmd(['ffprobe','-v','error','-show_format','-show_streams','-of','json',src]))},indent=2))
    (out/'templates.json').write_text(json.dumps(templates,indent=2));return templates

def manifest(template,duration):
    return [{**template[i%len(template)],'id':i} for i in range(duration)]
def trial(out,key,manifest,protocol,profile,repeat):
    folder=out/'trials'/f'{key}-{protocol}-{profile}-{repeat}';folder.mkdir(parents=True)
    (folder/'manifest.json').write_text(json.dumps(manifest))
    prefix='vb'+uuid.uuid4().hex[:9];s,r,d=[prefix+x for x in 'srd'];names=[];children=[];commands=[]
    def run(args):commands.append(list(map(str,args)));return cmd(args)
    def inside(ns,*args):return run(['ip','netns','exec',ns,*args])
    def counters():return [json.loads(inside(ns,'ip','-s','-j','link','show','eth0'))[0]['stats64']['tx'] for ns in (s,d)]
    try:
        for ns in (s,r,d):
            run(['ip','netns','add',ns]);names.append(ns);inside(ns,'ip','link','set','lo','up')
        for endpoint,dev,subnet in ((s,'left',10),(d,'right',20)):
            inside(endpoint,'ip','link','add','eth0','type','veth','peer','name',dev)
            inside(endpoint,'ip','link','set',dev,'netns',r)
            for ns,device,host in ((endpoint,'eth0',2),(r,dev,1)):
                inside(ns,'ip','addr','add',f'10.203.{subnet}.{host}/24','dev',device)
                inside(ns,'ip','link','set',device,'up')
                inside(ns,'/sbin/ethtool','-K',device,'tso','off','gso','off','gro','off')
            inside(endpoint,'ip','route','add','default','via',f'10.203.{subnet}.1')
        inside(r,'/sbin/sysctl','-qw','net.ipv4.ip_forward=1')
        inside(s,'/sbin/sysctl','-qw','net.ipv4.tcp_congestion_control=cubic')
        inside(s,'ping','-c','1','-W','2','10.203.20.2')
        logs=[]
        for role,ns in [('recv',d),('send',s)]:
            error=(folder/f'{role}.stderr').open('w');logs.append(error)
            p=subprocess.Popen(['ip','netns','exec',ns,sys.executable,str(out/'source/benchmarks/sustained_video/peer.py'),protocol,role,str(folder),str(out/'libkcp.so')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=error,text=True)
            children.append(p)
            if not select.select([p.stdout],[],[],5)[0] or p.stdout.readline()!='READY\n':raise RuntimeError(f'endpoint failed: {folder} {role}')
        receiver,sender=children
        for dev in ('left','right'):inside(r,'/sbin/tc','qdisc','replace','dev',dev,'root','netem','limit','1000',*PROFILES[profile])
        before=counters();sender.stdin.write('GO\n');sender.stdin.flush();sender.wait(timeout=len(manifest)+12)
        if sender.returncode:raise RuntimeError(f'sender error {folder}')
        after=counters();(folder/'stop').touch();receiver.wait(timeout=3)
        if receiver.returncode:raise RuntimeError(f'receiver error {folder}')
        start=json.loads((folder/'start.json').read_text());arrivals=[json.loads(x) for x in (folder/'arrivals.jsonl').read_text().splitlines()]
        result=score(arrivals,manifest,start)
        result.update(clip_codec=key,protocol=protocol,profile=profile,repeat=repeat,
            phase='screen' if len(manifest)==30 else 'confirm',
            tx_bytes=sum(a['bytes']-b['bytes'] for a,b in zip(after,before)),
            before=before,after=after,
            qdisc={dev:json.loads(inside(r,'/sbin/tc','-s','-j','qdisc','show','dev',dev)) for dev in ('left','right')})
        (folder/'result.json').write_text(json.dumps(result,indent=2))
        print(folder.name,f": {result['ontime_seconds']}/{len(manifest)} on time; stable={result['stable']}; lag growth={result['lag_growth_ms']}ms",flush=True)
        return result
    finally:
        for p in children:
            if p.poll() is None:p.kill();p.wait()
        for log in locals().get('logs',[]):log.close()
        for ns in reversed(names):subprocess.run(['ip','netns','del',ns],capture_output=True)
        (folder/'commands.json').write_text(json.dumps(commands,indent=2))

def report(out,results,metadata):
    data=json.dumps({'results':results,'metadata':metadata}).replace('<','\\u003c')
    (out/'results.json').write_text(json.dumps(results,indent=2))
    (out/'report.html').write_text((HERE/'report.html').read_text().replace('__DATA__',data))

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--clip',type=Path,required=True);p.add_argument('--jobs',type=int,default=1);a=p.parse_args()
    assert os.geteuid()==0 and a.jobs>0
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    hashes={}
    for src in [ROOT/'ikcp.c',ROOT/'ikcp.h',*HERE.glob('*.py'),HERE/'README.md',HERE/'report.html']:
        rel=src.relative_to(ROOT);dst=out/'source'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);hashes[str(rel)]=hashlib.sha256(src.read_bytes()).hexdigest()
    cmd(['/usr/bin/cc','-shared','-fPIC','-O2',out/'source/ikcp.c','-o',out/'libkcp.so'])
    metadata={'suite':'sustained-video-v1','jobs':a.jobs,'rates_mbps':RATES,'profiles':PROFILES,'source_hashes':hashes,'screen_s':30,'confirm_s':90,'confirm_repeats':2,'playout_offset_s':2,'max_lag_growth_ms':250,'ffmpeg':cmd(['ffmpeg','-version']).splitlines()[0]}
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2));templates=prepare(out,a.clip);results=[]
    def run_batch(cases,duration):
        random.Random(42).shuffle(cases)
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
            futures=[pool.submit(trial,out,key,manifest(templates[key],duration),proto,profile,repeat) for key,proto,profile,repeat in cases]
            for f in concurrent.futures.as_completed(futures):results.append(f.result());report(out,results,metadata)
    run_batch([(f'{rate:g}mbps',proto,profile,1) for rate,proto,profile in itertools.product(RATES,PROTOCOLS,PROFILES)],30)
    selected={};cases=[]
    for proto,profile in itertools.product(PROTOCOLS,PROFILES):
        passed=[RATES.index(float(r['clip_codec'][:-4])) for r in results if r['protocol']==proto and r['profile']==profile and r['stable']]
        ix=max(passed) if passed else 0;selected[proto,profile]=ix
        indices={ix,min(ix+1,len(RATES)-1)} if passed else {0}
        for index in indices:
            for repeat in (2,3):cases.append((f'{RATES[index]:g}mbps',proto,profile,repeat))
    (out/'screen-selection.json').write_text(json.dumps({f'{p}/{n}':RATES[ix] for (p,n),ix in selected.items()},indent=2))
    run_batch(cases,90)
    # Step down if the screen winner does not survive independent confirmation.
    while True:
        cases=[]
        for (proto,profile),ix in list(selected.items()):
            key=f'{RATES[ix]:g}mbps';rows=[r for r in results if r['phase']=='confirm' and r['clip_codec']==key and r['protocol']==proto and r['profile']==profile]
            assert len(rows)==2
            if not all(r['stable'] for r in rows) and ix>0:
                ix-=1;selected[proto,profile]=ix
                for rep in (2,3):cases.append((f'{RATES[ix]:g}mbps',proto,profile,rep))
        if not cases:break
        run_batch(cases,90)
    print('COMPLETE',len(results),'trials',out,flush=True)
if __name__=='__main__':main()
