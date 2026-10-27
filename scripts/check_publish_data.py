#!/usr/bin/env python3
"""Read-only consistency gate before publishing public Stillpoint data."""
import argparse
import json
import math
from pathlib import Path
import re


def number(value):
    try:
        value = float(str(value).replace(',', '').replace('−', '-').replace('%', ''))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


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
    feeds = extra.get('feeds', {})
    # Representative companies are a separately dated Yahoo batch. The public
    # CRWV card uses that batch, not necessarily the earlier standalone quote.
    crwv = feeds.get('names', {}).get('names', {}).get('CRWV') or feeds.get('crwv', {})
    expected_kpis = {
        0: prices.get('纳斯达克综合', {}).get('pct'),
        1: crwv.get('pct'),
        2: prices.get('VIX 波动率', {}).get('price'),
        3: prices.get('布伦特原油', {}).get('price'),
        4: feeds.get('cme', {}).get('year_end', {}).get('probability'),
        5: feeds.get('kr', {}).get('value'),
    }
    kpis = page.get('kpis', [])
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
