"""Hourly SGE Au99.99 threshold alerts to one fixed QQ owner. No model calls."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import fcntl
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8), 'Asia/Shanghai')
SOURCE = 'https://www.sge.com.cn/sjzx/yshqbg'
MOBILE_SOURCE = 'https://www.sge.com.cn/h5_sjzx/yshq'
ONEBOT_CONFIG = Path('/home/ubuntu/qq-codex/bridge/.private/config.json')
OWNER = '1000000001'
BOT = '1000000002'


def now_text():
    return datetime.now(TZ).isoformat(timespec='seconds')


class QuoteTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.text = [], []
        self.row, self.cell = None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        self.text.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip())
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row, self.cell = None, None


def parse_quote(html, fetched_at=None):
    p = QuoteTable()
    p.feed(html)
    match = re.search(r'上海黄金交易所\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*延时行情', ''.join(p.text))
    if not match:
        raise ValueError('Official delayed-quote date missing')
    date = datetime(*(int(x) for x in match.groups()), tzinfo=TZ).date()
    headings = [r for r in p.rows if '合约' in r and '最新价' in r]
    if len(headings) != 1:
        raise ValueError('Quote table headings changed')
    index = headings[0].index('最新价')
    rows = [r for r in p.rows if r and r[0] == 'Au99.99']
    if len(rows) != 1 or len(rows[0]) <= index:
        raise ValueError('Expected exactly one Au99.99 row')
    try:
        price = Decimal(rows[0][index].replace(',', ''))
    except InvalidOperation:
        raise ValueError('Invalid quote number') from None
    if not price.is_finite() or not Decimal('50') <= price <= Decimal('10000'):
        raise ValueError('Missing, zero or implausible quote')
    return {'symbol': 'Au99.99', 'price': str(price), 'unit': 'CNY/g',
            'trade_date': date.isoformat(), 'fetched_at': fetched_at or now_text(),
            'source': SOURCE, 'quote_kind': 'official_delayed'}


def fresh_quote(quote, now=None):
    now = datetime.now(TZ) if now is None else now.astimezone(TZ)
    day = datetime.strptime(quote['trade_date'], '%Y-%m-%d').date()
    # A night-session trading date may be tomorrow. Never call a prior day's page current.
    return day == now.date() or (now.hour >= 20 and day == (now + timedelta(days=1)).date())


def fetch_quote():
    attempts = [(SOURCE, True), (MOBILE_SOURCE, True), (SOURCE, False)]
    for url, proxy in attempts:
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler(
                {'https': 'http://127.0.0.1:17891'} if proxy else {}))
            request = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; PersonalGoldMonitor/1.0)',
                'Cache-Control': 'no-cache', 'Accept': 'text/html'})
            with opener.open(request, timeout=12 if proxy else 6) as response:
                if response.geturl() not in (SOURCE, MOBILE_SOURCE):
                    raise ValueError('Unexpected source redirect')
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise ValueError('Quote response oversized')
                quote = parse_quote(body.decode('utf-8'))
                quote['transport'] = 'existing_proxy' if proxy else 'direct'
                return quote
        except (OSError, ValueError, UnicodeError):
            continue
    raise ValueError('Official quote unavailable through all configured paths')


def zone_for(price, lower, upper):
    p, low, high = Decimal(str(price)), Decimal(str(lower)), Decimal(str(upper))
    if not all(v.is_finite() for v in (p, low, high)) or not 0 < low < high:
        raise ValueError('Invalid thresholds')
    return 'below' if p < low else 'above' if p > high else 'inside'


def alert_text(quote, zone, config):
    relation = '低于 ' + config['lower'] if zone == 'below' else '高于 ' + config['upper']
    return (f'小 C 金价提醒\n上金所 Au99.99：{quote["price"]} 元/克，已{relation} 元/克。\n'
            f'行情日期：{quote["trade_date"]}\n抓取时间：{quote["fetched_at"]}\n'
            f'数据为官方延时行情；同一侧持续越界不重复提醒。\n来源：{quote["source"]}')


class State:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS alerts(
                id INTEGER PRIMARY KEY,zone TEXT,quote TEXT,status TEXT,
                created TEXT,updated TEXT,message_id TEXT,reason TEXT);
        ''')
        with self.db:
            self.db.execute("UPDATE alerts SET status='uncertain',reason='process_interrupted_no_retry',updated=? WHERE status='sending'", (now_text(),))

    def get(self, key, default=None):
        row = self.db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO state VALUES(?,?)', (key, json.dumps(value)))

    def status(self):
        return {k: json.loads(v) for k, v in self.db.execute('SELECT key,value FROM state')}

    def observe(self, quote, config):
        zone = zone_for(quote['price'], config['lower'], config['upper'])
        with self.db:
            previous = self.get('zone')
            self.put('last_quote', quote)
            self.put('last_check', now_text())
            self.put('last_error', None)
            if zone != previous:
                self.db.execute("UPDATE alerts SET status='cancelled',updated=?,reason='zone_changed' WHERE status IN ('pending','queued')", (now_text(),))
                if zone != 'inside':
                    self.db.execute('INSERT INTO alerts(zone,quote,status,created,updated) VALUES(?,?,?,?,?)',
                                    (zone, json.dumps(quote), 'pending', now_text(), now_text()))
            self.put('zone', zone)
            row = self.db.execute("SELECT id FROM alerts WHERE zone=? AND status IN ('pending','queued') ORDER BY id DESC LIMIT 1", (zone,)).fetchone()
            if row:
                self.db.execute('UPDATE alerts SET quote=?,updated=? WHERE id=?', (json.dumps(quote), now_text(), row[0]))
            return row[0] if row else None

    def mark(self, event, status, reason=None, message_id=None):
        with self.db:
            self.db.execute('UPDATE alerts SET status=?,updated=?,reason=?,message_id=? WHERE id=?',
                            (status, now_text(), reason, str(message_id) if message_id is not None else None, event))

    def error(self, reason):
        with self.db:
            self.put('last_check', now_text())
            self.put('last_error', reason)


class QQ:
    def __init__(self):
        config = json.loads(ONEBOT_CONFIG.read_text())
        if str(config['owner_qq']) != OWNER or str(config['bot_qq']) != BOT or config['onebot_url'] != 'http://127.0.0.1:13001':
            raise ValueError('Unexpected QQ identity or endpoint')
        self.config = config
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, action, payload):
        req = urllib.request.Request(self.config['onebot_url']+'/'+action,
            data=json.dumps(payload).encode(), headers={
                'Authorization': 'Bearer '+self.config['onebot_token'], 'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=15) as response:
            result = json.loads(response.read(65536))
        if result.get('status') != 'ok' or result.get('retcode') != 0:
            raise ValueError('QQ operation was not confirmed')
        return result.get('data') or {}

    def ready(self):
        state = self.request('get_status', {})
        identity = self.request('get_login_info', {})
        return state.get('online') is True and state.get('good') is True and str(identity.get('user_id')) == BOT

    def send(self, text):
        return self.request('send_private_msg', {'user_id': int(OWNER), 'auto_escape': True,
            'message': [{'type': 'text', 'data': {'text': text}}]})


def deliver(state, event, quote, config, qq=None):
    # Preflight failure is safe to retry on a later fresh quote. An uncertain send is not.
    try:
        qq = QQ() if qq is None else qq
        if not qq.ready():
            raise ValueError('QQ offline')
    except Exception:
        state.mark(event, 'queued', 'qq_unavailable_before_send')
        return 'queued_qq_offline'
    state.mark(event, 'sending')  # durable before the side effect
    try:
        result = qq.send(alert_text(quote, zone_for(quote['price'], config['lower'], config['upper']), config))
        if result.get('message_id') is None:
            raise ValueError('No delivery identifier')
        state.mark(event, 'sent', message_id=result['message_id'])
        return 'sent'
    except Exception:
        state.mark(event, 'uncertain', 'send_not_confirmed_no_automatic_retry')
        return 'uncertain_no_retry'


def load_config():
    config = json.loads((ROOT/'.private/config.json').read_text())
    if config.get('symbol') != 'Au99.99' or config.get('unit') != 'CNY/g':
        raise ValueError('Unexpected instrument or currency')
    zone_for('850', config['lower'], config['upper'])
    return config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Fetch/validate only; no state change and no QQ send')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    private = ROOT/'.private'
    private.mkdir(mode=0o700, exist_ok=True)
    config = load_config()
    if args.dry_run:
        q = fetch_quote()
        print(json.dumps({'quote': q, 'fresh': fresh_quote(q), 'zone': zone_for(q['price'], config['lower'], config['upper']), 'notification_sent': False}, ensure_ascii=False))
        return 0
    with (private/'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"status":"already_running"}')
            return 0
        state = State(private/'state.sqlite3')
        try:
            if args.status:
                print(json.dumps({'config': config, 'state': state.status(), 'last_alerts': state.db.execute('SELECT id,zone,status,created,reason FROM alerts ORDER BY id DESC LIMIT 5').fetchall()}, ensure_ascii=False))
                return 0
            try:
                quote = fetch_quote()
                if not fresh_quote(quote):
                    state.error('source_trade_date_not_current')
                    print(json.dumps({'status': 'skipped_stale_quote', 'trade_date': quote['trade_date']}))
                    return 0
                event = state.observe(quote, config)
                delivery = deliver(state, event, quote, config) if event else 'not_required'
                print(json.dumps({'status': 'checked', 'quote': quote, 'zone': state.get('zone'), 'delivery': delivery}, ensure_ascii=False))
                return 0
            except Exception as exc:
                state.error(type(exc).__name__)
                print(json.dumps({'status': 'check_failed', 'error_type': type(exc).__name__, 'notification_sent': False}))
                return 1
        finally:
            state.db.close()


if __name__ == '__main__':
    raise SystemExit(main())
