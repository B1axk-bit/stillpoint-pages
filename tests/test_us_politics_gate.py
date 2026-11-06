import copy
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('gate',Path(__file__).resolve().parents[1]/'scripts/check_publish_data.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
class PoliticsGate(unittest.TestCase):
    def review(self):
        return dict(schema_version=1,mode='research_only',scope='US',status='available',evaluated_at='2026-11-06T15:40:00+08:00',reviewed_at='2026-11-06T15:30:00+08:00',next_review_at='2026-11-07T07:00:00+08:00',summary='观察',observations=[dict(title='许可程序',fact='已核事实',kind='event',category='产业',stage='procedure',sources=[dict(title='原件',url='https://example.gov/policy',published_at='2026-09-21',checked_at='2026-11-06T15:20:00+08:00',status='primary')])],coverage=[],limits=[])
    def test_old_pages_and_current_safe_research_both_work(self):
        self.assertEqual(gate.validate_politics_review(None,None),[]);r=self.review();self.assertEqual(gate.validate_politics_review(r,copy.deepcopy(r)),[])
    def test_private_activation_requires_matching_public_research(self):
        self.assertTrue(gate.validate_politics_review(None,self.review()))
    def test_dates_stage_or_content_cannot_drift(self):
        for key,value in [('reviewed_at','2026-11-05T15:30:00+08:00'),('status','available-but-unverified'),('summary','wrong')]:
            r=self.review();p=copy.deepcopy(r);p[key]=value;self.assertTrue(gate.validate_politics_review(p,r))
    def test_private_fields_and_paths_are_rejected_even_if_expected_has_them(self):
        r=self.review();r['observations'][0]['source_path']='analysis/evidence/private.json';self.assertTrue(gate.validate_politics_review(r,r))
    def test_automatic_mode_and_unsafe_source_are_not_accepted(self):
        r=self.review();r['mode']='automatic_risk';self.assertTrue(gate.validate_politics_review(r,r));r=self.review();r['observations'][0]['sources'][0]['url']='javascript:alert(1)';self.assertTrue(gate.validate_politics_review(r,r))
if __name__=='__main__':unittest.main()
