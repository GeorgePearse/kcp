#!/usr/bin/env python3
"""video-v1: real encoded payloads over isolated TCP/KCP/UDP paths."""
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

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PROFILES={'20mbps':['delay','20ms','rate','20mbit'], '1mbps':['delay','20ms','rate','1mbit'], '5mbps':['delay','20ms','rate','5mbit'], '5mbps_loss1':['delay','20ms','loss','1%','rate','5mbit']}
def cmd(args):
    p=subprocess.run(list(map(str,args)),check=True,text=True,capture_output=True)
    return p.stdout

def prepare(out,clips):
    manifests={}; records=[]
    for item in clips:
        name,src=item.split('=',1); src=Path(src).resolve()
        if not name.replace('_','').isalnum():raise ValueError('clip name must be alphanumeric')
        probe=json.loads(cmd(['ffprobe','-v','error','-show_format','-show_streams','-of','json',src]))
        assert float(probe['format']['duration'])>=4
        records.append({'name':name,'source':str(src),'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'probe':probe})
        for codec in ['h264','mjpeg']:
            key=f'{name}-{codec}'; folder=out/'media'/key; folder.mkdir(parents=True)
            segments=[]
            for sid in range(4):
                dst=folder/f'{sid}.mkv'
                command=['ffmpeg','-v','error','-nostdin','-threads','2','-ss',str(sid),'-i',src,'-t','1','-an','-vf','fps=10,scale=1920:1080','-threads','2']
                command+=['-c:v','libx264','-preset','veryfast','-crf','23','-bf','0','-g','10','-pix_fmt','yuv420p'] if codec=='h264' else ['-c:v','mjpeg','-q:v','4','-pix_fmt','yuvj420p']
                command+=[dst];cmd(command)
                # Decode every segment, not only inspect its container metadata.
                decode=cmd(['ffmpeg','-v','error','-xerror','-threads','2','-i',dst,'-f','framemd5','-'])
                frames=sum(1 for line in decode.splitlines() if line and not line.startswith('#'))
                assert frames==10,(dst,frames)
                (folder/f'{sid}.framemd5').write_text(decode)
                blob=dst.read_bytes()
                segments.append({'id':sid,'path':str(dst),'size':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),'frames':frames,'command':list(map(str,command))})
            manifests[key]=segments
            print(key,'encoded Mbps',round(sum(x['size'] for x in segments)*8/4e6,3),flush=True)
    (out/'inputs.json').write_text(json.dumps(records,indent=2))
    (out/'manifests.json').write_text(json.dumps(manifests,indent=2))
    return manifests

def score(arrivals, manifest, start):
    completions=[x for x in arrivals if 'complete' in x and x['time']<=start+7]
    assert len({x['complete'] for x in completions})==len(completions)
    ontime=[x for x in completions if x['time']<=start+x['complete']+1.5]
    payload=sum(x['bytes'] for x in arrivals if 'bytes' in x and not x['duplicate'] and x['time']<=start+7)
    return completions, ontime, payload

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
            p=subprocess.Popen(['ip','netns','exec',ns,sys.executable,str(out/'source/benchmarks/video/peer.py'),protocol,role,str(folder),str(out/'libkcp.so')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=error,text=True)
            children.append(p)
            if not select.select([p.stdout],[],[],5)[0] or p.stdout.readline()!='READY\n':raise RuntimeError(f'endpoint failed: {folder} {role}')
        receiver,sender=children
        for dev in ('left','right'):inside(r,'/sbin/tc','qdisc','replace','dev',dev,'root','netem','limit','1000',*PROFILES[profile])
        before=counters();sender.stdin.write('GO\n');sender.stdin.flush();sender.wait(timeout=12)
        if sender.returncode:raise RuntimeError(f'sender error {folder}')
        after=counters();(folder/'stop').touch();receiver.wait(timeout=3)
        if receiver.returncode:raise RuntimeError(f'receiver error {folder}')
        start=json.loads((folder/'start.json').read_text());arrivals=[json.loads(x) for x in (folder/'arrivals.jsonl').read_text().splitlines()]
        completions,ontime,payload=score(arrivals,manifest,start)
        offered=sum(x['size'] for x in manifest)
        result={'clip_codec':key,'protocol':protocol,'profile':profile,'repeat':repeat,'offered_bytes':offered,'encoded_mbps':offered*8/4e6,'received_payload_bytes':payload,'complete_seconds':len(completions),'ontime_seconds':len(ontime),'offered_seconds':4,'usable_bytes':sum(manifest[x['complete']]['size'] for x in completions),'tx_bytes':sum(a['bytes']-b['bytes'] for a,b in zip(after,before)),'completion_latency_ms':[(x['time']-start-x['complete'])*1000 for x in completions],'before':before,'after':after,'qdisc':{dev:json.loads(inside(r,'/sbin/tc','-s','-j','qdisc','show','dev',dev)) for dev in ('left','right')}}
        (folder/'result.json').write_text(json.dumps(result,indent=2))
        print(folder.name,f": {len(completions)}/4 seconds complete, {len(ontime)}/4 on time",flush=True)
        return result
    finally:
        for p in children:
            if p.poll() is None:p.kill();p.wait()
        for log in locals().get('logs',[]):log.close()
        for ns in reversed(names):subprocess.run(['ip','netns','del',ns],capture_output=True)
        (folder/'commands.json').write_text(json.dumps(commands,indent=2))

def report(out,results,metadata):
    data=json.dumps({'results':results,'metadata':metadata}).replace('<','\\u003c')
    (out/'report.html').write_text((HERE/'report.html').read_text().replace('__DATA__',data))

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--clip',action='append',required=True);p.add_argument('--jobs',type=int,default=1);p.add_argument('--repeats',type=int,default=2);p.add_argument('--profiles',nargs='+',choices=PROFILES,default=list(PROFILES));p.add_argument('--protocols',nargs='+',choices=['tcp','kcp','udp'],default=['tcp','kcp','udp']);a=p.parse_args()
    assert os.geteuid()==0 and a.jobs>0 and a.repeats>0
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    source_hashes={}
    for src in [ROOT/'ikcp.c',ROOT/'ikcp.h',*HERE.glob('*.py'),HERE/'README.md',HERE/'report.html']:
        rel=src.relative_to(ROOT);dst=out/'source'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);source_hashes[str(rel)]=hashlib.sha256(src.read_bytes()).hexdigest()
    cmd(['/usr/bin/cc','-shared','-fPIC','-O2',out/'source/ikcp.c','-o',out/'libkcp.so'])
    metadata={'suite':'video-v1','jobs':a.jobs,'repeats':a.repeats,'source_hashes':source_hashes,'profiles':PROFILES,'ffmpeg':cmd(['ffmpeg','-version']).splitlines()[0],'limitations':'Pre-encoded independent 1s segments; 1.5s deadline; 7s observation; exact SHA256 required; no partial decode credit; fixed settings not matched quality; unseeded loss; no encryption; CPU shared between concurrent trials.'}
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2))
    manifests=prepare(out,a.clip)
    cases=list(itertools.product(manifests,a.protocols,a.profiles,range(1,a.repeats+1)));random.Random(42).shuffle(cases)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures=[pool.submit(trial,out,key,manifests[key],proto,prof,rep) for key,proto,prof,rep in cases]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result());(out/'results.json').write_text(json.dumps(results,indent=2));report(out,results,metadata)
    print('COMPLETE',len(results),'trials',out,flush=True)
if __name__=='__main__':main()
