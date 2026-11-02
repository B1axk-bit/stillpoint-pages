#!/usr/bin/env python3
"""Read-only consistency gate before publishing public Stillpoint data."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import re
import urllib.parse


def number(value):
    try:
        value = float(str(value).replace(',', '').replace('−', '-').replace('%', ''))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


FLOW_KIND = 'eastmoney_market_capital_flow'
FLOW_SCOPE = 'eastmoney_sh_sz'
FLOW_HISTORY_FIELDS = ('main_net_yi', 'super_large_net_yi', 'large_net_yi',
                       'medium_net_yi', 'small_net_yi', 'main_net_pct')


def flow_number(value):
    """Money fields are normalized values, never percentages or display dashes."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(',', '').replace('−', '-'))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def validate_capital_flow(public, source, now=None):
    """Check the optional public flow projection without changing investment rules."""
    issues = []
    zone = dt.timezone(dt.timedelta(hours=8))
    clock = now or dt.datetime.now(zone)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=zone)
    clock, today = clock.astimezone(zone), clock.astimezone(zone).date()

    def fail(message):
        issues.append('沪深资金流：' + message)

    def day(value):
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return None
        try:
            result = dt.date.fromisoformat(value)
        except ValueError:
            return None
        return result if result <= today else None

    def timestamp(value):
        if not isinstance(value, str):
            return None
        try:
            result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
        return (result if result.tzinfo else result.replace(tzinfo=zone)).astimezone(zone)

    def same_amount(actual, expected, label):
        a, b = flow_number(actual), flow_number(expected)
        if expected is None:
            if actual is not None:
                fail(label + '缺值被填成数值或占位字符串')
        elif b is None or a is None or abs(a - b) > 0.011:
            fail(label + '与正式来源不一致或不是有限值')

    def usable(data):
        if not isinstance(data, dict):
            return False
        history = data.get('history')
        return flow_number(data.get('value')) is not None or (
            isinstance(history, list) and any(isinstance(r, dict) and
            flow_number(r.get('main_net_yi')) is not None for r in history))

    if source is None and public is None:
        return issues  # Existing fixtures and pre-feature archives stay compatible.
    if not isinstance(source, dict):
        if public is not None:
            fail('页面没有对应的正式采集来源')
        return issues

    def check_contract(data, label):
        if data.get('unit') != '亿元':
            fail(label + '单位必须为亿元')
        if data.get('scope_id') != FLOW_SCOPE:
            fail(label + '范围必须为东财沪深口径，不能冒充全A')
        if data.get('source_kind') != FLOW_KIND or data.get('feed_kind') != FLOW_KIND:
            fail(label + '来源身份不是独立公开东财资金流')
        url = data.get('source_url')
        try:
            parsed = urllib.parse.urlsplit(url) if isinstance(url, str) else None
            host = parsed.hostname if parsed else None
        except ValueError:
            host, parsed = None, None
        if not host or parsed.scheme not in ('https', 'http') or not (
                host == 'eastmoney.com' or host.endswith('.eastmoney.com')):
            fail(label + '缺公开东财来源地址或误用了私有来源')
        if data.get('status') not in ('ok', 'partial', 'carried', 'failed'):
            fail(label + '来源状态不明')
        if data.get('status') == 'failed' and usable(data):
            fail(label + '失败状态仍含读数，应隔离或保留旧日并标carried')
        if data.get('retrieved_at') is not None:
            retrieved = timestamp(data['retrieved_at'])
            if retrieved is None or retrieved > clock:
                fail(label + '读取时间非法或在未来')
        for key in ('value', 'sum5_yi', 'sum20_yi'):
            if data.get(key) is not None and flow_number(data[key]) is None:
                fail(label + key + '不是有限金额')
        if usable(data) and day(data.get('date')) is None:
            fail(label + '实际观测日期缺失、非法或在未来')
        history = data.get('history')
        if history is None:
            history = []
        if not isinstance(history, list):
            fail(label + '历史必须为数组')
            return []
        if usable(data) and not history:
            fail(label + '已有净额但缺对应历史交易日')
        complete = data.get('history_complete', True)
        history_errors = data.get('history_errors')
        if history_errors is None:
            history_errors = []
        if (not isinstance(complete, bool) or not isinstance(history_errors, list) or
                any(not isinstance(x, str) or not x.strip() for x in history_errors)):
            fail(label + '历史完整性标记无效')
            complete, history_errors = False, []
        if history_errors and complete:
            fail(label + '已知历史缺口却标成完整窗口')
        if not complete and usable(data) and not history_errors:
            fail(label + '历史不完整却缺少具体隔离原因')
        dates, nets = [], []
        for row in history:
            if not isinstance(row, dict):
                fail(label + '历史行结构无效')
                continue
            stamp = row.get('date')
            if day(stamp) is None:
                fail(label + '历史含缺失、非法或未来日期')
            dates.append(stamp)
            net = flow_number(row.get('main_net_yi'))
            if net is None:
                fail(label + '历史净额缺失或非有限值')
            nets.append(net)
            for key in FLOW_HISTORY_FIELDS[1:]:
                if row.get(key) is not None and flow_number(row[key]) is None:
                    fail(label + '历史' + key + '不是有限值')
        if dates and (any(not isinstance(x, str) for x in dates) or len(set(dates)) != len(dates)
                      or dates != sorted(dates)):
            fail(label + '历史交易日重复或未按日期递增')
        if history and isinstance(history[-1], dict):
            if data.get('date') != history[-1].get('date'):
                fail(label + '最新日期与历史末项不一致')
            same_amount(data.get('value'), history[-1].get('main_net_yi'), label + '最新净额')
        for window in (5, 20):
            key = 'sum%d_yi' % window
            expected = sum(nets[-window:]) if complete and len(nets) >= window and all(x is not None for x in nets[-window:]) else None
            same_amount(data.get(key), expected, label + '%d日累计' % window)
            count = data.get('sum%d_count' % window)
            expected_count = min(window, len(history)) if complete else 0
            if count is not None and count != expected_count:
                fail(label + '%d日累计窗口数错误' % window)
            reason = data.get('sum%d_reason' % window)
            if not complete and usable(data) and (count != 0 or not isinstance(reason, str) or not reason.strip()):
                fail(label + '%d日历史缺口未隔离累计或未说明原因' % window)
        current = data.get('current')
        if current is not None:
            if not isinstance(current, dict):
                fail(label + '当日买卖金额结构无效')
            else:
                if current.get('date') != data.get('date') or day(current.get('date')) is None:
                    fail(label + '当日买卖金额日期与净额错配')
                if current.get('unit') != '亿元':
                    fail(label + '当日买卖金额单位错误')
                incoming, outgoing, net = (flow_number(current.get(k)) for k in ('inflow_yi', 'outflow_yi', 'net_yi'))
                if None in (incoming, outgoing, net) or incoming < 0 or outgoing < 0:
                    fail(label + '当日买卖金额缺失、非有限或毛额为负')
                else:
                    same_amount(incoming - outgoing, net, label + '买卖差额')
                    same_amount(net, data.get('value'), label + '当日净额')
                observed = current.get('observed_at')
                observed_time = timestamp(observed)
                if observed_time is None or observed_time.date() != day(current.get('date')):
                    fail(label + '买卖金额来源时点与实际日期错配')
                elif observed_time > clock:
                    fail(label + '买卖金额来源时间在未来')
        return history

    source_history = check_contract(source, '来源')
    if public is None:
        if usable(source):
            fail('正式来源已有可用值，但页面未展示')
        return issues
    if not isinstance(public, dict):
        fail('页面板块结构无效')
        return issues
    public_history = check_contract(public, '页面')
    for key in ('date', 'unit', 'scope_id', 'source_kind', 'feed_kind', 'status', 'source_url'):
        if public.get(key) != source.get(key):
            fail('页面' + key + '未与正式来源一致')
    for key in ('sum5_count', 'sum20_count'):
        if key in source and public.get(key) != source[key]:
            fail('页面' + key + '与来源不一致')
    for key in ('history_complete', 'history_errors', 'sum5_reason', 'sum20_reason'):
        if key in source and public.get(key) != source[key]:
            fail('页面' + key + '未保留历史缺口资格')
    for key in ('value', 'sum5_yi', 'sum20_yi'):
        same_amount(public.get(key), source.get(key), '页面' + key)
    if len(public_history) != len(source_history):
        fail('页面历史窗口与正式来源不一致')
    for actual, expected in zip(public_history, source_history):
        if not isinstance(actual, dict) or not isinstance(expected, dict):
            continue
        if actual.get('date') != expected.get('date'):
            fail('页面历史日期被替换或错位')
        for key in FLOW_HISTORY_FIELDS:
            same_amount(actual.get(key), expected.get(key), '页面历史' + key)
    a, b = public.get('current'), source.get('current')
    if b is None:
        if a is not None:
            fail('来源缺当日买卖毛额，页面却补造毛额')
    elif not isinstance(a, dict):
        fail('来源已有当日买卖毛额，页面漏展示')
    elif isinstance(b, dict):
        for key in ('date', 'unit', 'observed_at'):
            if a.get(key) != b.get(key):
                fail('页面当日买卖' + key + '与来源不一致')
        for key in ('inflow_yi', 'outflow_yi', 'net_yi'):
            same_amount(a.get(key), b.get(key), '页面当日' + key)
    return issues


def validate(page, latest, snapshot, extra, production=True):
    issues = []
    theme = next((x for x in latest.get('themes', []) if x.get('theme') == page.get('mainline', {}).get('theme')), None)
    if not theme:
        return ['公开主线与私有当前计算没有匹配主题']
    mainline, signals = page.get('mainline', {}), page.get('signals', {})
    for label, public, expected in [
        ('主线分数', mainline.get('score'), theme.get('score')),
        ('当前格', mainline.get('cell'), theme.get('cell')),
        ('减仓档', signals.get('derisk', {}).get('tier'), theme.get('derisk', {}).get('tier')),
    ]:
        if public != expected:
            issues.append(label + '未与本轮计算一致')
    for lamp in latest.get('lamps', []):
        public = signals.get('tally', {}).get('lamps', {}).get(lamp['n'], {})
        if any(public.get(k) != lamp.get(k) for k in ['raw', 'confirmed', 'stress', 'calm']):
            issues.append(lamp['n'] + '计票/确认色不一致')
    prices = {p.get('name'): p for p in snapshot.get('prices', [])}
    public_review = mainline.get('review') or {}
    private_review = theme.get('research_review') or {}
    if public_review and any(public_review.get(k) != private_review.get(k)
                             for k in ['asof', 'status', 'review_complete', 'summary']):
        issues.append('前后台复检日期或结论未同步')
    feeds = extra.get('feeds', {})
    ashare = page.get('ashare') or {}
    issues.extend(validate_capital_flow(ashare.get('capitalFlow') if isinstance(ashare, dict) else None,
                                       feeds.get('ashare_capital_flow')))
    # Representative companies are a separately dated Yahoo batch. The public
    # CRWV card uses that batch, not necessarily the earlier standalone quote.
    crwv = feeds.get('names', {}).get('names', {}).get('CRWV') or feeds.get('crwv', {})
    cme = feeds.get('cme') or {}
    year_end = cme.get('year_end') or {}
    kpis = page.get('kpis', [])
    cme_scope = kpis[4].get('probabilityScope', 'year_end') if len(kpis) > 4 else 'year_end'
    if cme_scope not in ('year_end', 'nearest_meeting'):
        issues.append('CME关键数字的概率范围不明')
    cme_value = cme.get('value') if cme_scope == 'nearest_meeting' else year_end.get('probability')
    if cme_scope == 'nearest_meeting' and kpis[4].get('meeting') != cme.get('next_meeting'):
        issues.append('CME关键数字的会议日期不一致')
    if len(kpis) > 4 and cme_value is None and number(kpis[4].get('value')) is not None:
        issues.append('CME缺合格读数时仍显示数字')
    expected_kpis = {
        0: prices.get('纳斯达克综合', {}).get('pct'),
        1: crwv.get('pct'),
        2: prices.get('VIX 波动率', {}).get('price'),
        3: prices.get('布伦特原油', {}).get('price'),
        4: cme_value,
        5: feeds.get('kr', {}).get('value'),
    }
    if len(kpis) != 6:
        issues.append('关键数字应保留六项')
    else:
        for i, expected in expected_kpis.items():
            value = number(kpis[i].get('value'))
            if expected is not None and (value is None or abs(value - expected) > 0.011):
                issues.append('关键数字%d与实际来源不一致' % (i + 1))
        if kpis[5].get('colorBy') != 'netFlow':
            issues.append('外资净流量缺少正负方向语义')
    encoded = json.dumps(page, ensure_ascii=False)
    for marker in ['t.wind.com.cn/', 'windcode', 'buy_anchor', 'user_confirmed_buy', 'wind_responses']:
        if marker in encoded:
            issues.append('公开数据出现私有原始材料标记：' + marker)
    if any(key in mainline for key in ['items', 'fading']):
        issues.append('公开主线包含私有研究账本明细')
    if production and any('预览' in str(text) for text in [page.get('brand', {}).get('meta'), page.get('edition', {}).get('label'), page.get('header', {}).get('edition')]):
        issues.append('正式发布仍带本机预览标签')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--page', default=str(Path(__file__).resolve().parents[1] / 'index.html'))
    parser.add_argument('--data-root', required=True)
    parser.add_argument('--allow-preview', action='store_true')
    args = parser.parse_args()
    text = Path(args.page).read_text(encoding='utf-8')
    matches = re.findall(r'<script type="application/json" id="page-data">(.*?)</script>', text, re.S)
    if len(matches) != 1:
        raise SystemExit('page-data必须恰好一份')
    root = Path(args.data_root)
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    latest = read(root / 'confidence/latest.json')
    name = latest['snapshot']
    if Path(name).name != name or not name.endswith('.json'):
        raise SystemExit('快照路径不合规')
    issues = validate(json.loads(matches[0]), latest, read(root / 'snapshots' / name), read(root / 'snapshots/extra_latest.json'), not args.allow_preview)
    for issue in issues:
        print('未通过：' + issue)
    if issues:
        raise SystemExit(1)
    print('公开数字、主线、风险档、灯色与来源一致；隐私标记及发布标签检查通过。')


if __name__ == '__main__':
    main()
