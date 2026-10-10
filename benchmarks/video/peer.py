"""Actual socket endpoints shared by the video-v1 transports."""
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import select
import socket
import struct
import sys
import time

HEADER = struct.Struct('!III')
PAYLOAD = 1140
class KCP:
    def __init__(self, library, sock, remote):
        self.lib = C.CDLL(library)
        self.lib.ikcp_create.argtypes = [C.c_uint32, C.c_void_p]
        self.lib.ikcp_create.restype = C.c_void_p
        for name, args in {'ikcp_send':[C.c_void_p,C.c_char_p,C.c_int], 'ikcp_input':[C.c_void_p,C.c_char_p,C.c_long], 'ikcp_recv':[C.c_void_p,C.c_void_p,C.c_int], 'ikcp_update':[C.c_void_p,C.c_uint32], 'ikcp_nodelay':[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_int], 'ikcp_wndsize':[C.c_void_p,C.c_int,C.c_int], 'ikcp_setmtu':[C.c_void_p,C.c_int]}.items():
            getattr(self.lib,name).argtypes=args
        self.k = self.lib.ikcp_create(12345,None)
        callback=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_int,C.c_void_p,C.c_void_p)
        def output(buf,n,k,user):
            try: sock.sendto(C.string_at(buf,n),remote[0]); return 0
            except (BlockingIOError,TypeError): return -1
        self.callback=callback(output)
        self.lib.ikcp_setoutput.argtypes=[C.c_void_p,callback]
        self.lib.ikcp_setoutput(self.k,self.callback)
        self.lib.ikcp_nodelay(self.k,1,10,2,0)
        self.lib.ikcp_wndsize(self.k,128,128)
        self.lib.ikcp_setmtu(self.k,1200)
        self.buffer=C.create_string_buffer(65536)
    def send(self,data):
        assert self.lib.ikcp_send(self.k,data,len(data))==len(data)
    def input(self,data):
        assert self.lib.ikcp_input(self.k,data,len(data))==0
    def tick(self): self.lib.ikcp_update(self.k,int(time.monotonic()*1000)&0xffffffff)
    def messages(self):
        while True:
            n=self.lib.ikcp_recv(self.k,self.buffer,len(self.buffer))
            if n<0:return
            yield self.buffer.raw[:n]

def main():
    protocol,role,folder,library=sys.argv[1:]
    folder=Path(folder); manifest=json.loads((folder/'manifest.json').read_text())
    tcp=protocol=='tcp'; sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024*1024)
    remote=[('10.203.20.2',9400)]
    if role=='recv':
        sock.bind(('0.0.0.0',9400))
        if tcp:
            sock.listen(1); print('READY',flush=True); sock,_=sock.accept()
        else: print('READY',flush=True)
    else:
        if tcp:sock.connect(remote[0])
        print('READY',flush=True)
    if tcp:sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
    sock.setblocking(False)
    kcp=KCP(library,sock,remote) if protocol=='kcp' else None
    if role=='send':
        packets=[]
        for seg in manifest:
            data=Path(seg['path']).read_bytes(); n=math.ceil(len(data)/PAYLOAD)
            for i in range(n):
                packets.append((seg['id']+i/n,HEADER.pack(seg['id'],i,n)+data[i*PAYLOAD:(i+1)*PAYLOAD]))
        sys.stdin.readline()
        start=time.monotonic(); (folder/'start.json').write_text(json.dumps(start))
        pending=bytearray(); cursor=0
        while time.monotonic()<start+7:
            now=time.monotonic()
            while cursor<len(packets) and start+packets[cursor][0]<=now:
                data=packets[cursor][1]
                if tcp:pending.extend(struct.pack('!I',len(data))+data)
                elif kcp:kcp.send(data)
                else:
                    try:sock.sendto(data,remote[0])
                    except BlockingIOError:pass
                cursor+=1
            if tcp and pending:
                try:
                    n=sock.send(pending); del pending[:n]
                except BlockingIOError:pass
            if kcp:
                while True:
                    try:data,_=sock.recvfrom(65536); kcp.input(data)
                    except BlockingIOError:break
                kcp.tick()
            time.sleep(.001)
        assert cursor==len(packets),'sender could not submit the offered schedule'
        (folder/'sender.json').write_text(json.dumps({'start':start,'offered_packets':len(packets),'submitted_packets':cursor,'tcp_unsent_bytes':len(pending)}))
        return
    parts={}; completed=set(); stream=bytearray(); rows=[]; stop=time.monotonic()+20
    with (folder/'arrivals.jsonl').open('w',buffering=1) as output:
        def accept(data):
            now=time.monotonic()
            assert len(data)>HEADER.size
            sid,part,total=HEADER.unpack_from(data); assert sid<len(manifest)
            spec=manifest[sid]; assert total==math.ceil(spec['size']/PAYLOAD) and part<total
            payload=data[HEADER.size:]
            assert len(payload)==min(PAYLOAD,spec['size']-part*PAYLOAD)
            bucket=parts.setdefault(sid,{})
            duplicate=part in bucket
            if duplicate: assert bucket[part]==payload
            else:bucket[part]=payload
            output.write(json.dumps({'segment':sid,'part':part,'time':now,'bytes':len(payload),'duplicate':duplicate})+'\n')
            if len(bucket)==total and sid not in completed:
                blob=b''.join(bucket[i] for i in range(total))
                assert hashlib.sha256(blob).hexdigest()==spec['sha256'],'payload mismatch'
                completed.add(sid)
                output.write(json.dumps({'complete':sid,'time':now,'sha256':spec['sha256']})+'\n')
        while time.monotonic()<stop:
            if (folder/'stop').exists():break
            if select.select([sock],[],[],.001)[0]:
                if tcp:
                    data=sock.recv(65536)
                    if not data:break
                    stream.extend(data)
                    while len(stream)>=4:
                        n=struct.unpack_from('!I',stream)[0]; assert 12<n<=1200
                        if len(stream)<4+n:break
                        accept(bytes(stream[4:4+n]));del stream[:4+n]
                else:
                    data,addr=sock.recvfrom(65536);remote[0]=addr
                    if kcp:kcp.input(data)
                    else:accept(data)
            if kcp:
                kcp.tick()
                for data in kcp.messages():accept(data)
if __name__=='__main__':main()
