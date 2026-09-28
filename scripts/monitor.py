#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
游戏活动监控：抓 B 站官号动态 -> 正则提取「卡池/活动 + 日期区间」-> events.json
只保留卡池和活动两类；签到/版本/维护/抽奖自动丢弃。
多 RSSHub 公共实例轮换；单游戏抓取失败时保留该游戏旧数据。
"""
import json, re, sys, html, hashlib, urllib.request, datetime
from xml.etree import ElementTree as ET

GAMES = [
    {'name': '明日方舟',            'uid': '161775300'},
    {'name': '明日方舟：终末地',    'uid': '1265652806'},
    {'name': '无期迷途',            'uid': '647409444'},
    {'name': '女神异闻录：夜幕魅影', 'uid': '1606210274'},
]
RSS_HUBS = [
    'https://rsshub.app',
    'https://rsshub.rssforever.com',
    'https://rsshub.ktachibana.party',
    'https://rsshub.pseudoyu.com',
]

KW_GACHA  = re.compile(r'卡池|寻访|追踪')
KW_EVENT  = re.compile(r'活动|SideStory|故事集|危机合约|赛季|玩法')
RANGE_RE  = re.compile(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日[^0-9年月日]{0,16}?[~～—–\-至到]{1,3}\s*(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*日')
SINGLE_RE = re.compile(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日')
TAG_RE    = re.compile(r'<[^>]+>')
YEAR = datetime.date.today().year

def norm_year(m, d):
    """无年份月日推断：活动日历只关心前后两三个月"""
    today = datetime.date.today()
    if m in (11, 12) and today.month <= 2: return YEAR - 1   # 今年1-2月看到11-12月=去年
    if m <= 2 and today.month >= 11:       return YEAR + 1   # 今年11-12月看到1-2月=明年
    return YEAR

def to_date(m, d):
    try:
        return datetime.date(norm_year(m, d), m, d)
    except ValueError:
        return None

def clean(txt):
    txt = TAG_RE.sub(' ', txt or '')
    return html.unescape(re.sub(r'\s+', ' ', txt)).strip()

def fetch_rss(uid):
    path = '/bilibili/user/dynamic/%s' % uid
    for hub in RSS_HUBS:
        try:
            req = urllib.request.Request(hub + path, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
            root = ET.fromstring(body)
            items = root.findall('.//item')
            if items:
                print('  ok via %s (%d items)' % (hub, len(items)))
                return items
        except Exception as e:
            print('  fail via %s: %s' % (hub, e))
    return None

def classify(text):
    if KW_GACHA.search(text): return '卡池'
    if KW_EVENT.search(text): return '活动'
    return None

def extract(text, title, guid, game):
    """从动态文本提取事件列表"""
    etype = classify(text)
    if not etype:
        return []
    out, seen = [], set()
    for m in RANGE_RE.finditer(text):
        s = to_date(int(m.group(1)), int(m.group(2)))
        e = to_date(int(m.group(3) or m.group(1)), int(m.group(4)))
        if s and e and e >= s:
            out.append((s, e))
    if not out:
        m = SINGLE_RE.search(text)
        if m and re.search(r'开启|上线|发售|开催|更新', text):
            s = to_date(int(m.group(1)), int(m.group(2)))
            if s: out.append((s, s))
    today = datetime.date.today()
    res = []
    for s, e in out:
        if e < today - datetime.timedelta(days=7):   continue  # 已结束太久
        if s > today + datetime.timedelta(days=60):  continue  # 太远期
        key = (s, e)
        if key in seen: continue
        seen.add(key)
        h = hashlib.md5(('%s|%s|%s' % (guid, s, e)).encode()).hexdigest()[:10]
        res.append({
            'id': 'auto-' + h, 'game': game, 'type': etype,
            'title': title, 'start': s.isoformat(), 'end': e.isoformat(),
            'source': 'auto',
        })
    return res

def main():
    # 读旧数据：按游戏保留，失败的游戏用旧数据兜底
    old = {}
    try:
        with open('events.json', encoding='utf-8') as f:
            for e in json.load(f).get('events', []):
                old.setdefault(e['game'], []).append(e)
    except Exception:
        pass

    events, failed = [], []
    for g in GAMES:
        print('[%s] uid=%s' % (g['name'], g['uid']))
        items = fetch_rss(g['uid'])
        if items is None:
            print('  ALL instances failed, keep old data')
            failed.append(g['name'])
            events.extend(old.get(g['name'], []))
            continue
        got = []
        for it in items:
            title = clean(it.findtext('title'))[:26]
            desc  = clean(it.findtext('description'))
            guid  = it.findtext('guid') or it.findtext('link') or ''
            got.extend extract if False else extract(desc, title, guid, g['name'])
        print('  extracted %d events' % len(got))
        events.extend(got)

    payload = {
        'generatedAt': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
        'failedGames': failed,
        'events': sorted(events, key=lambda x: (x['game'], x['start'])),
    }
    with open('events.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print('total events: %d, failed games: %s' % (len(events), failed or 'none'))

if __name__ == '__main__':
    main()
