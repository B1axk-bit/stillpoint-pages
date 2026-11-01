import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('gate', Path(__file__).resolve().parents[1] / 'scripts/check_publish_data.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class PublishGate(unittest.TestCase):
    def setUp(self):
        self.page = {'brand': {'meta': '正式更新'}, 'edition': {'label': '研究'},
                     'mainline': {'theme': '美股 AI', 'score': 75, 'cell': 'H1'},
                     'signals': {'derisk': {'tier': 2}, 'tally': {'lamps': {}}},
                     'kpis': [{'value': '+1'}, {'value': '+2'}, {'value': '18'}, {'value': '100'},
                              {'value': '80'}, {'value': '1,234', 'colorBy': 'netFlow'}]}
        self.latest = {'themes': [{'theme': '美股 AI', 'score': 75, 'cell': 'H1', 'derisk': {'tier': 2}}], 'lamps': []}
        self.snapshot = {'prices': [{'name': '纳斯达克综合', 'pct': 1}, {'name': 'VIX 波动率', 'price': 18}, {'name': '布伦特原油', 'price': 100}]}
        self.extra = {'feeds': {'crwv': {'pct': 2}, 'cme': {'year_end': {'probability': 80}}, 'kr': {'value': 1234}}}

    def errors(self):
        return gate.validate(self.page, self.latest, self.snapshot, self.extra)

    def test_consistent_sources(self):
        self.assertEqual(self.errors(), [])

    def test_reject_only_timestamp_update_with_stale_number(self):
        self.snapshot['prices'][0]['pct'] = 3
        self.assertTrue(any('关键数字1' in e for e in self.errors()))

    def test_reject_changed_score_or_action(self):
        self.page['mainline']['score'] = 85
        self.page['signals']['derisk']['tier'] = 1
        self.assertEqual(len(self.errors()), 2)

    def test_private_evidence_and_preview_cannot_be_published(self):
        self.page['mainline']['items'] = [{'buy_anchor': 123}]
        self.page['brand']['meta'] = '更新预览'
        self.assertEqual(len(self.errors()), 3)

    def test_missing_values_are_not_zero(self):
        self.page['kpis'][0]['value'] = '—'
        self.assertTrue(self.errors())
        self.assertIsNone(gate.number('—'))

    def test_header_chip_cannot_keep_an_old_preview_label(self):
        self.page['header'] = {'edition': '更新预览'}
        self.assertTrue(any('预览' in e for e in self.errors()))

    def test_public_net_flow_direction_contract(self):
        self.page['kpis'][5].pop('colorBy')
        self.assertTrue(any('净流量' in e for e in self.errors()))

    def test_separately_dated_company_quote_is_not_mixed_with_standalone(self):
        self.extra['feeds']['names'] = {'names': {'CRWV': {'pct': 3}}}
        self.assertTrue(any('关键数字2' in e for e in self.errors()))
        self.page['kpis'][1]['value'] = '+3'
        self.assertEqual(self.errors(), [])

    def test_null_year_end_is_missing_and_does_not_crash(self):
        self.extra['feeds']['cme']['year_end'] = None
        self.assertTrue(any('缺合格读数' in e for e in self.errors()))
        self.page['kpis'][4]['value'] = '—'
        self.assertEqual(self.errors(), [])

    def test_nearest_meeting_requires_its_own_value_and_date(self):
        self.extra['feeds']['cme'].update(value=72, next_meeting='2026-12-09', year_end=None)
        self.page['kpis'][4].update(value='72', probabilityScope='nearest_meeting', meeting='2026-12-09')
        self.assertEqual(self.errors(), [])
        self.page['kpis'][4]['meeting'] = '2026-10-28'
        self.assertTrue(any('会议日期' in e for e in self.errors()))

    def test_nearest_probability_cannot_silently_fill_year_end(self):
        self.extra['feeds']['cme'].update(value=72, next_meeting='2026-12-09', year_end=None)
        self.page['kpis'][4]['value'] = '72'
        self.assertTrue(any('缺合格读数' in e for e in self.errors()))

    def test_new_public_review_cannot_leave_backend_on_previous_run(self):
        self.page['mainline']['review'] = dict(asof='2026-11-02', status='completed_conditional_H1', review_complete=True, summary='当前复检')
        self.latest['themes'][0]['research_review'] = dict(asof='2026-10-30', status='completed_conditional_H1', review_complete=True, summary='此前复检')
        self.assertTrue(any('复检日期或结论' in e for e in self.errors()))
        self.latest['themes'][0]['research_review'] = copy.deepcopy(self.page['mainline']['review'])
        self.assertEqual(self.errors(), [])


if __name__ == '__main__':
    unittest.main()
