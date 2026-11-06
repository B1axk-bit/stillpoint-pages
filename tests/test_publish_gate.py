import copy
import datetime as dt
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

    def install_risk_control(self):
        control = dict(version='v1.4.0', evaluated_at='2026-11-06T14:30:00+08:00',
                       market_date='2026-11-05', status='active', minimum_tier=2,
                       next_review_at='2026-11-07T06:00:00+08:00',
                       reasons=[dict(id='theme', label='主题承接受损', tier=2, status='active',
                                     reason='融资约束与本主题价格承接受损并存',
                                     release_condition='取得对应缓解证据',
                                     next_review_at='2026-11-07T06:00:00+08:00')],
                       downgrade=dict(allowed=False, clear_periods=0, required_periods=2,
                                      blockers=['本主题承接受损尚未解除']))
        for dr in (self.page['signals']['derisk'], self.latest['themes'][0]['derisk']):
            dr.update(legacy=dict(tier=1, raw=1), control=copy.deepcopy(control))
        return self.page['signals']['derisk'], self.latest['themes'][0]['derisk']

    def test_risk_control_allows_public_summary_and_keeps_score_version_separate(self):
        self.install_risk_control()
        self.latest['version'] = 'v1.3.2'
        self.assertEqual(self.errors(), [])

    def test_risk_control_cannot_be_omitted_after_private_activation(self):
        public, private = self.install_risk_control()
        public.pop('control')
        self.assertTrue(any('风险衔接' in e for e in self.errors()))

    def test_risk_control_compares_version_dates_and_legacy_tier(self):
        for key, value in [('version', 'v1.3.2'), ('market_date', '2026-11-04'),
                           ('evaluated_at', '2026-11-06T09:23:00+08:00'),
                           ('next_review_at', '2026-11-09T06:00:00+08:00')]:
            with self.subTest(field=key):
                public, private = self.install_risk_control()
                public['control'][key] = value
                self.assertTrue(any('风险衔接' in e for e in self.errors()))
        public, private = self.install_risk_control()
        public['legacy']['tier'] = 0
        self.assertTrue(any('旧规则对照' in e for e in self.errors()))

    def test_risk_control_cannot_hide_unresolved_reasons_or_clear_periods(self):
        public, private = self.install_risk_control()
        public['control']['reasons'] = []
        public['control']['downgrade'].update(blockers=[], clear_periods=2, allowed=True)
        errors = self.errors()
        self.assertTrue(any('阻止降档' in e for e in errors))
        self.assertTrue(any('降档解除' in e for e in errors))
        self.assertTrue(any('风险约束' in e for e in errors))

    def test_risk_control_rejects_private_material_and_tier_below_floor(self):
        public, private = self.install_risk_control()
        public['control']['reasons'][0]['source_path'] = 'analysis/evidence/private.json'
        self.assertTrue(any('白名单' in e or '私有路径' in e for e in self.errors()))
        public, private = self.install_risk_control()
        public['control']['minimum_tier'] = private['control']['minimum_tier'] = 3
        self.assertTrue(any('最低风险约束' in e for e in self.errors()))

    def test_risk_control_malformed_rows_do_not_crash_gate(self):
        for rows in (1, {}, ['broken']):
            public, private = self.install_risk_control()
            public['control']['reasons'] = rows
            self.assertTrue(self.errors())

    def flow(self, count=20):
        dates, day = [], dt.date(2026, 9, 14)
        while len(dates) < count:
            if day.weekday() < 5:
                dates.append(day.isoformat())
            day += dt.timedelta(days=1)
        history = [dict(date=day, main_net_yi=i - 10,
                        super_large_net_yi=(i - 10) / 2, large_net_yi=(i - 10) / 2,
                        medium_net_yi=-(i - 10) / 2, small_net_yi=-(i - 10) / 2,
                        main_net_pct=(i - 10) / 100) for i, day in enumerate(dates)]
        last = history[-1]
        return dict(value=last['main_net_yi'], date=last['date'], unit='亿元',
                    scope_id='eastmoney_sh_sz', source_kind=gate.FLOW_KIND, feed_kind=gate.FLOW_KIND,
                    status='ok', source='东方财富沪深市场资金流',
                    source_url='https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get',
                    retrieved_at='2026-10-12T16:12:00+08:00', history=history,
                    sum5_yi=sum(x['main_net_yi'] for x in history[-5:]) if count >= 5 else None,
                    sum20_yi=sum(x['main_net_yi'] for x in history[-20:]) if count >= 20 else None,
                    sum5_count=min(5, count), sum20_count=min(20, count),
                    current=dict(date=last['date'], unit='亿元', inflow_yi=20 + last['main_net_yi'],
                                 outflow_yi=20, net_yi=last['main_net_yi'],
                                 observed_at=last['date'] + 'T16:00:00+08:00'))

    def install_flow(self, count=20):
        flow = self.flow(count)
        self.extra['feeds']['ashare_capital_flow'] = flow
        self.page['ashare'] = {'capitalFlow': copy.deepcopy(flow)}
        return flow, self.page['ashare']['capitalFlow']

    def test_capital_flow_full_public_projection_passes(self):
        self.install_flow()
        self.assertEqual(self.errors(), [])

    def test_capital_flow_available_source_cannot_be_omitted(self):
        self.extra['feeds']['ashare_capital_flow'] = self.flow()
        self.assertTrue(any('页面未展示' in e for e in self.errors()))

    def test_capital_flow_page_without_formal_source_rejected(self):
        self.page['ashare'] = {'capitalFlow': self.flow()}
        self.assertTrue(any('正式采集来源' in e for e in self.errors()))

    def test_capital_flow_missing_current_gross_is_legal_partial(self):
        source, public = self.install_flow()
        for data in (source, public):
            data.update(status='partial', current=None)
        self.assertEqual(self.errors(), [])
        public['current'] = dict(date=public['date'], unit='亿元', inflow_yi=0, outflow_yi=0, net_yi=0)
        self.assertTrue(any('补造毛额' in e for e in self.errors()))

    def test_capital_flow_carried_old_day_is_not_relabelled_as_retrieval_day(self):
        source, public = self.install_flow()
        for data in (source, public):
            data.update(status='carried', retrieved_at='2026-11-02T16:00:00+08:00')
        self.assertEqual(self.errors(), [])
        public['date'] = '2026-11-02'
        self.assertTrue(any('日期' in e or 'date' in e for e in self.errors()))

    def test_capital_flow_unit_scope_and_provenance_are_not_interchangeable(self):
        for key, value in [('unit', '元'), ('scope_id', 'wind_all_a'),
                           ('source_kind', 'wind'), ('feed_kind', 'wind'),
                           ('source_url', 'https://t.wind.com.cn/api/quote'),
                           ('source_url', 'https://eastmoney.com.example.com/flow')]:
            with self.subTest(field=key, value=value):
                self.install_flow()
                self.page['ashare']['capitalFlow'][key] = value
                self.assertTrue(self.errors())

    def test_capital_flow_gross_is_same_day_and_reconciles_to_net(self):
        for field, value in [('date', '2026-10-08'), ('net_yi', 200),
                             ('inflow_yi', -1), ('outflow_yi', float('inf')),
                             ('unit', '元'), ('observed_at', '2026-10-08T16:00:00+08:00')]:
            with self.subTest(field=field):
                source, public = self.install_flow()
                public['current'][field] = value
                self.assertTrue(self.errors())

    def test_capital_flow_five_and_twenty_day_sums_are_recomputed(self):
        for key in ('sum5_yi', 'sum20_yi'):
            with self.subTest(key=key):
                source, public = self.install_flow()
                source[key] += 1
                public[key] += 1
                self.assertTrue(any('累计' in e for e in self.errors()))

    def test_capital_flow_short_windows_do_not_become_zero(self):
        source, public = self.install_flow(count=3)
        self.assertEqual(self.errors(), [])
        public['sum5_yi'] = 0
        self.assertTrue(any('缺值' in e for e in self.errors()))

    def test_capital_flow_known_history_gap_does_not_fill_window_with_surviving_rows(self):
        source, public = self.install_flow()
        for data in (source, public):
            data.update(status='partial', history_complete=False, history_errors=['历史第8行数据无效已隔离'],
                        sum5_yi=None, sum20_yi=None, sum5_count=0, sum20_count=0,
                        sum5_reason='历史有缺口，不拼接剩余行', sum20_reason='历史有缺口，不拼接剩余行')
        self.assertEqual(self.errors(), [])
        for data in (source, public):
            data['sum5_yi'] = sum(r['main_net_yi'] for r in data['history'][-5:])
            data['sum5_count'] = 5
        self.assertTrue(any('累计' in e or '缺值' in e for e in self.errors()))

    def test_capital_flow_history_errors_cannot_claim_complete_window(self):
        source, public = self.install_flow()
        for data in (source, public):
            data.update(history_complete=True, history_errors=['一行无效'])
        self.assertTrue(any('已知历史缺口' in e for e in self.errors()))

    def test_capital_flow_current_error_does_not_remove_valid_historical_sums(self):
        source, public = self.install_flow()
        for data in (source, public):
            data.update(status='partial', current=None, history_complete=True,
                        history_errors=[], errors=['当前毛额读取失败'])
        self.assertEqual(self.errors(), [])

    def test_capital_flow_real_zero_is_valid_and_still_requires_projection(self):
        source, public = self.install_flow(count=11)
        self.assertEqual(source['value'], 0)
        self.assertEqual(self.errors(), [])
        self.page.pop('ashare')
        self.assertTrue(any('页面未展示' in e for e in self.errors()))

    def test_capital_flow_nonfinite_source_and_public_values_are_rejected(self):
        for value in (float('nan'), float('inf'), '—', True, '10%'):
            with self.subTest(value=value):
                source, public = self.install_flow()
                source['value'] = public['value'] = value
                self.assertTrue(self.errors())

    def test_capital_flow_future_or_duplicate_history_days_are_rejected(self):
        source, public = self.install_flow()
        public['history'][-1]['date'] = '2099-01-02'
        self.assertTrue(any('未来' in e for e in self.errors()))
        source, public = self.install_flow()
        public['history'][1]['date'] = public['history'][0]['date']
        self.assertTrue(any('重复' in e for e in self.errors()))

    def test_capital_flow_same_day_future_quote_time_is_rejected(self):
        source = self.flow()
        source['retrieved_at'] = '2026-10-09T15:00:00+08:00'
        clock = dt.datetime(2026, 10, 9, 15, 30, tzinfo=dt.timezone(dt.timedelta(hours=8)))
        issues = gate.validate_capital_flow(source, copy.deepcopy(source), now=clock)
        self.assertTrue(any('来源时间在未来' in e for e in issues))

    def test_capital_flow_history_is_not_replaced_by_a_different_window(self):
        source, public = self.install_flow()
        public['history'][0]['main_net_yi'] += 1
        self.assertTrue(self.errors())
        source, public = self.install_flow()
        public['history'] = public['history'][1:]
        self.assertTrue(any('窗口' in e for e in self.errors()))

    def test_capital_flow_null_category_is_not_filled_with_zero(self):
        source, public = self.install_flow()
        source['history'][0]['medium_net_yi'] = None
        public['history'][0]['medium_net_yi'] = None
        self.assertEqual(self.errors(), [])
        public['history'][0]['medium_net_yi'] = 0
        self.assertTrue(any('缺值' in e for e in self.errors()))

    def test_capital_flow_malformed_history_does_not_crash_gate(self):
        for malformed in ({}, ['bad row'], [dict(date=['bad'], main_net_yi=0)]):
            with self.subTest(history=malformed):
                source, public = self.install_flow()
                public['history'] = malformed
                self.assertTrue(self.errors())

    def test_capital_flow_failed_empty_source_is_legal_without_display(self):
        source = self.flow()
        source.update(status='failed', value=None, date=None, history=[], current=None,
                      sum5_yi=None, sum20_yi=None, sum5_count=0, sum20_count=0)
        self.extra['feeds']['ashare_capital_flow'] = source
        self.assertEqual(self.errors(), [])
        source['value'], source['date'] = 0, '2026-10-09'
        self.assertTrue(self.errors())


if __name__ == '__main__':
    unittest.main()
