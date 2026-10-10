import unittest
from metrics import score

class Stability(unittest.TestCase):
    def rows(self,n=30,lag=1.1):return [{'complete':i,'time':100+i+lag} for i in range(n)]
    def manifest(self,n=30):return [{'size':1000} for _ in range(n)]
    def test_steady_stream_passes(self):
        r=score(self.rows(),self.manifest(),100)
        self.assertTrue(r['stable']);self.assertEqual(r['minimum_extra_stall_s'],0)
    def test_one_missing_segment_fails_even_with_high_byte_delivery(self):
        r=score(self.rows()[:-1]+[{'bytes':30000,'duplicate':False,'time':102}],self.manifest(),100)
        self.assertFalse(r['stable']);self.assertEqual(r['deadline_failure_seconds'],1);self.assertTrue(r['stall_is_lower_bound'])
    def test_late_complete_stream_stalls(self):
        r=score(self.rows(lag=2.4),self.manifest(),100)
        self.assertFalse(r['stable']);self.assertAlmostEqual(r['minimum_extra_stall_s'],.4)
    def test_growth_fails_before_buffer_exhaustion(self):
        rows=[{'complete':i,'time':100+i+1+i*.02} for i in range(30)]
        r=score(rows,self.manifest(),100)
        self.assertEqual(r['deadline_failure_seconds'],0);self.assertFalse(r['stable']);self.assertGreater(r['lag_growth_ms'],250)
    def test_after_cutoff_never_counts(self):
        rows=self.rows();rows[-1]['time']=136
        self.assertEqual(score(rows,self.manifest(),100)['complete_seconds'],29)
    def test_duplicate_completion_rejected(self):
        with self.assertRaises(AssertionError):score(self.rows()+self.rows()[:1],self.manifest(),100)
if __name__=='__main__':unittest.main()
