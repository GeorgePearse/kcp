import ctypes
from pathlib import Path
import socket
import tempfile
import subprocess
import time
import unittest
from run import score,ROOT
from peer import KCP

class Metrics(unittest.TestCase):
    def test_partial_bytes_are_not_usable_video(self):
        complete,ontime,received=score([{'bytes':100,'duplicate':False,'time':1}],[],0)
        self.assertEqual((complete,ontime,received),([],[],100))
    def test_deadline_and_cutoff(self):
        complete,ontime,received=score([{'complete':0,'time':1.5},{'complete':1,'time':2.6},{'complete':2,'time':7.1}],[],0)
        self.assertEqual(len(complete),2);self.assertEqual(len(ontime),1)
    def test_duplicate_and_late_bytes(self):
        _,_,received=score([{'bytes':10,'duplicate':False,'time':1},{'bytes':10,'duplicate':True,'time':2},{'bytes':20,'duplicate':False,'time':7.1}],[],0)
        self.assertEqual(received,10)
    def test_kcp_actual_library_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            lib=str(Path(d)/'kcp.so')
            subprocess.run(['/usr/bin/cc','-shared','-fPIC','-O2',str(ROOT/'ikcp.c'),'-o',lib],check=True)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as a,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as b:
                for sock in (a,b):sock.bind(('127.0.0.1',0));sock.setblocking(False)
                ka=KCP(lib,a,[b.getsockname()]);kb=KCP(lib,b,[a.getsockname()])
                payload=b'x'*1152;ka.send(payload);received=[];end=time.monotonic()+2
                while time.monotonic()<end and not received:
                    for sock,k in [(a,ka),(b,kb)]:
                        try:data,_=sock.recvfrom(65536);k.input(data)
                        except BlockingIOError:pass
                        k.tick()
                    received.extend(kb.messages());time.sleep(.001)
                self.assertEqual(received,[payload])
if __name__=='__main__':unittest.main()
