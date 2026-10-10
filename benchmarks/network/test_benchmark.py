import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import unittest

from metrics import summarize_rows
from compare import compare


class DeliveryAccounting(unittest.TestCase):
    def score(self, rows, reliable=False):
        return summarize_rows(rows, 5, 10000, 1000000, 4000000, 100, reliable)

    def test_udp_gaps_duplicates_and_reordering(self):
        rows = [(0, 1000000, 1002000), (2, 1020000, 1022000),
                (2, 1020000, 1023000), (1, 1010000, 1050000),
                (4, 1040000, 1240000)]
        result = self.score(rows)
        self.assertEqual(result['received'], 4)
        self.assertEqual(result['missing'], 1)
        self.assertEqual(result['within_100ms'], 3)
        self.assertEqual(result['duplicate_arrivals'], 1)
        self.assertEqual(result['reordered_unique'], 1)

    def test_observation_cutoff_does_not_earn_credit(self):
        r = self.score([(0, 1000000, 5050001), (1, 1010000, 5050002)], reliable=True)
        self.assertEqual(r['received'], 0)
        self.assertEqual(r['arrivals_after_window'], 2)
        self.assertIsNone(r['p95_ms'])

    def test_reliable_gap_and_duplicate_are_rejected(self):
        for rows in ([(1, 1010000, 1012000)], [(0, 1000000, 1002000)]*2):
            with self.assertRaises(ValueError):
                self.score(rows, reliable=True)

    def test_forged_timestamp_or_sequence_is_rejected(self):
        for rows in ([(0, 999999, 1002000)], [(5, 1050000, 1052000)], [(0, 1000000, 999999)]):
            with self.assertRaises(ValueError):
                self.score(rows)

    def test_udp_cannot_win_reliable_comparison(self):
        with self.assertRaises(ValueError):
            compare([{'protocol': 'udp', 'delivery_contract': 'best-effort datagrams'}], 'kcp', 'udp')

    def test_missing_candidate_trials_rejected(self):
        row = dict(protocol='kcp', delivery_contract='reliable ordered', profile='clean',
                   repeat=1, offered=5, netem=['delay','2ms'])
        with self.assertRaises(ValueError):
            compare([row], 'kcp', 'kcp_iw10')


@unittest.skipUnless(os.environ.get('PEER_BINARY'), 'Set PEER_BINARY for actual UDP receiver checks')
class RealUdpReceiver(unittest.TestCase):
    def run_receiver(self, messages, success):
        proc = subprocess.Popen([os.environ['PEER_BINARY'], 'udp', 'recv', '127.0.0.1', '5', '10000'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertTrue(select.select([proc.stdout], [], [], 3)[0])
            self.assertEqual(proc.stdout.readline(), 'READY\n')
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                for message in messages:
                    sock.sendto(message, ('127.0.0.1', 19090))
            if success:
                # Wait for the final message to be handled, without pipe buffering races.
                import time
                time.sleep(.1)
                proc.terminate()
            stdout, stderr = proc.communicate(timeout=3)
            self.assertEqual(proc.returncode == 0, success, stderr)
            return stdout
        finally:
            if proc.poll() is None:
                proc.kill(); proc.wait()
            proc.stdout.close(); proc.stderr.close()

    def packet(self, seq):
        return struct.pack('=QQ', seq, 1000000+seq*10000) + bytes((seq+i)%256 for i in range(16,256))

    def test_receiver_preserves_udp_arrival_order_and_duplicates(self):
        order = [0, 2, 2, 1, 4]
        output = self.run_receiver([self.packet(i) for i in order], True)
        self.assertEqual([int(line.split(',')[0]) for line in output.splitlines()], order)

    def test_receiver_rejects_corrupt_payload(self):
        packet = bytearray(self.packet(0)); packet[-1] ^= 1
        self.run_receiver([packet], False)

    def test_receiver_rejects_out_of_range_sequence(self):
        self.run_receiver([self.packet(5)], False)


if __name__ == '__main__':
    unittest.main()
