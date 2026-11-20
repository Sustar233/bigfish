"""Changsha commute forecast to one fixed QQ recipient, with durable deduplication."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import fcntl
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, '/home/ubuntu/gold-watch')
from gold_watch import QQ

ROOT = Path(__file__).resolve().parent
TZ = ZoneInfo('Asia/Shanghai')
LOCATION = 'latitude=28.2282&longitude=112.9388&timezone=Asia%2FShanghai&forecast_days=1'
WEATHER = ('https://api.open-meteo.com/v1/forecast?' + LOCATION +
           '&hourly=precipitation_probability,precipitation&daily=temperature_2m_max,temperature_2m_min')
AIR = ('https://air-quality-api.open-meteo.com/v1/air-quality?' + LOCATION +
       '&current=us_aqi,pm2_5')
METNO = 'https://api.met.no/weatherapi/locationforecast/2.0/complete?lat=28.2282&lon=112.9388'


def fetch(url):
    for proxy in ({}, {'https': 'http://127.0.0.1:17891'}):
        try:
            op = urllib.request.build_opener(urllib.request.ProxyHandler(proxy))
            req = urllib.request.Request(url, headers={'User-Agent': 'PersonalChangshaWeather/1.0'})
            with op.open(req, timeout=18) as response:
                if response.geturl() != url:
                    raise ValueError('unexpected_redirect')
                body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError('response_too_large')
            data = json.loads(body)
            if (url != METNO and data.get('timezone') != 'Asia/Shanghai') or data.get('error'):
                raise ValueError('invalid_source_response')
            return data
        except (OSError, ValueError):
            continue
    raise RuntimeError('public_source_unavailable')


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError('missing_numeric_data')
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError('out_of_range_data')
    return value


def commute(hourly, day, start, end, allow_missing_probability=False):
    """Precipitation at 09:00 covers 08:00-09:00, not 09:00-10:00."""
    left = datetime.fromisoformat(day + 'T' + start).replace(tzinfo=TZ)
    right = datetime.fromisoformat(day + 'T' + end).replace(tzinfo=TZ)
    samples = []
    for i, stamp in enumerate(hourly.get('time', [])):
        moment = datetime.fromisoformat(stamp).replace(tzinfo=TZ)
        if moment > left and moment - timedelta(hours=1) < right:
            raw = hourly['precipitation_probability'][i]
            p = None if raw is None and allow_missing_probability else number(raw, 0, 100)
            amount = number(hourly['precipitation'][i], 0, 500)
            samples.append((moment, p, amount))
    expected = [left.replace(minute=0) + timedelta(hours=i + 1)
                for i in range(math.ceil((right-left.replace(minute=0)).total_seconds()/3600))]
    if [x[0] for x in samples] != expected:
        raise ValueError('incomplete_commute_forecast')
    probabilities = [x[1] for x in samples if x[1] is not None]
    p = max(probabilities) if len(probabilities) == len(samples) else None
    wet = any(x[2] >= 0.1 for x in samples)
    if p is None:
        return '预报有降水，把伞带上稳妥些' if wet else '预报暂时没看到明显降水，出门前仍可能变'
    if p >= 60:
        wording = '下雨可能性比较大，伞带上'
    elif p >= 30:
        wording = '有可能碰上雨，带把伞稳妥些'
    elif wet:
        wording = '预报有一点降水，还是把伞放包里吧'
    else:
        wording = '下雨可能性不大，但也不是保证一滴不下'
    return f'{wording}（小时降雨概率最高{p:.0f}%）'


def air_line(data, now):
    try:
        current = data['current']
        stamp = datetime.fromisoformat(current['time']).replace(tzinfo=TZ)
        if not timedelta(minutes=-10) <= now-stamp <= timedelta(hours=2):
            raise ValueError('stale_air_data')
        aqi = number(current['us_aqi'], 0, 1000)
        pm = number(current['pm2_5'], 0, 2000)
        label = ('优' if aqi <= 50 else '良' if aqi <= 100 else
                 '对敏感人群不健康' if aqi <= 150 else '不健康' if aqi <= 200 else
                 '很不健康' if aqi <= 300 else '危险')
        return (f'空气这边，{stamp:%H:%M}的模型估算是美标AQI {aqi:.0f}，{label}，'
                f'PM2.5约{pm:.1f}微克/立方米。这个是模型估算，不是本地站点实测。')
    except (KeyError, TypeError, ValueError):
        return '空气数据这次没取到够新的，指数就先不瞎报了。'


def render(weather, air, now, observed_at=None):
    observed_at = observed_at or now
    day = now.date().isoformat()
    if weather.get('timezone') != 'Asia/Shanghai':
        raise ValueError('wrong_weather_timezone')
    daily = weather['daily']
    if daily['time'] != [day]:
        raise ValueError('forecast_date_not_today')
    low = number(daily['temperature_2m_min'][0], -50, 60)
    high = number(daily['temperature_2m_max'][0], -50, 60)
    if low > high:
        raise ValueError('invalid_temperature_range')
    missing_ok = weather.get('provider') == 'MET Norway'
    morning = commute(weather['hourly'], day, '08:30', '10:00', missing_ok)
    evening = commute(weather['hourly'], day, '18:00', '19:00', missing_ok)
    scope = '从早上到今晚' if missing_ok else '今天'
    provider = weather.get('provider', 'Open-Meteo')
    return (f'大人，长沙{scope}大概{low:.0f}到{high:.0f}℃。出门前的天气，我先给你看过了。\n\n'
            f'上班那段，08:30—10:00，{morning}。\n'
            f'下班18:00—19:00，{evening}。\n\n'
            f'{air_line(air, observed_at)}\n\n'
            f'这是{observed_at:%m月%d日 %H:%M}查到的城区预报，早上看晚上的雨，临近出门还可能变。'
            f'\n天气：{provider}；空气：CAMS / Open-Meteo。')


def metno_weather(now):
    """Reuse identical global forecasts for 3h, as requested by MET Norway."""
    cache = ROOT / '.private' / 'metno-cache.json'
    wall_now = datetime.now(TZ)
    data = None
    try:
        saved = json.loads(cache.read_text())
        age = wall_now-datetime.fromisoformat(saved['fetched_at'])
        if timedelta(0) <= age < timedelta(hours=3):
            data = saved['data']
    except (OSError, ValueError, KeyError):
        pass
    if data is None:
        data = fetch(METNO)
        cache.parent.mkdir(mode=0o700, exist_ok=True)
        cache.write_text(json.dumps({'fetched_at': wall_now.isoformat(), 'data': data}))
    updated = datetime.fromisoformat(data['properties']['meta']['updated_at'].replace('Z', '+00:00'))
    if not timedelta(minutes=-10) <= wall_now-updated <= timedelta(hours=12):
        raise ValueError('stale_metno_forecast')
    day = now.date().isoformat()
    temperatures = []
    hourly = {'time': [], 'precipitation_probability': [], 'precipitation': []}
    for row in data['properties']['timeseries']:
        start = datetime.fromisoformat(row['time'].replace('Z', '+00:00')).astimezone(TZ)
        if start.date() == now.date() and start.hour >= 6:
            temperatures.append(number(row['data']['instant']['details']['air_temperature'], -50, 60))
        details = row['data'].get('next_1_hours', {}).get('details')
        if details is not None:
            hourly['time'].append((start+timedelta(hours=1)).replace(tzinfo=None).isoformat())
            hourly['precipitation_probability'].append(details.get('probability_of_precipitation'))
            hourly['precipitation'].append(details.get('precipitation_amount'))
    if len(temperatures) < 12:
        raise ValueError('incomplete_temperature_day')
    return {'timezone': 'Asia/Shanghai', 'provider': 'MET Norway', 'hourly': hourly,
            'daily': {'time': [day], 'temperature_2m_min': [min(temperatures)],
                      'temperature_2m_max': [max(temperatures)]}}


def weather_data(now):
    try:
        data = metno_weather(now)
        # Validate the commute coverage before selecting this source.
        render(data, {}, now)
        return data
    except Exception:
        return fetch(WEATHER)


class State:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS deliveries(day TEXT PRIMARY KEY,status TEXT,'
                        'updated TEXT,message_id TEXT,error TEXT)')
        # An interrupted in-flight send may already have reached QQ. Never resend it blindly.
        with self.db:
            self.db.execute("UPDATE deliveries SET status='uncertain',error='interrupted_send' WHERE status='sending'")

    def get(self, day):
        row = self.db.execute('SELECT status FROM deliveries WHERE day=?', (day,)).fetchone()
        return row[0] if row else None

    def put(self, day, status, now, message_id=None, error=None):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO deliveries VALUES(?,?,?,?,?)',
                            (day, status, now.isoformat(), str(message_id) if message_id is not None else None, error))


def deliver(state, now, text, qq):
    day = now.date().isoformat()
    if state.get(day) in ('sent', 'uncertain', 'sending'):
        return 'already_handled'
    try:
        if not qq.ready():
            raise RuntimeError('qq_offline')
    except Exception:
        state.put(day, 'queued', now, error='qq_not_ready')
        return 'queued'
    state.put(day, 'sending', now)
    try:
        result = qq.send(text)
        if result.get('message_id') is None:
            raise RuntimeError('no_message_id')
        state.put(day, 'sent', now, message_id=result['message_id'])
        return 'sent'
    except Exception:
        state.put(day, 'uncertain', now, error='send_outcome_uncertain_no_retry')
        return 'uncertain'


def collect(now, observed_at=None):
    with ThreadPoolExecutor(max_workers=2) as pool:
        weather_future = pool.submit(weather_data, now)
        air_future = pool.submit(fetch, AIR)
        weather = weather_future.result()
        try:
            air = air_future.result()
        except Exception:
            air = {}
    return render(weather, air, now, observed_at)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    now = datetime.now(TZ)
    os.umask(0o077)
    if args.dry_run:
        target = now if now.hour < 8 else (now+timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
        print(json.dumps({'preview': collect(target, now), 'forecast_date': target.date().isoformat(),
                          'preview_only': True, 'notification_sent': False}, ensure_ascii=False))
        return 0
    private = ROOT / '.private'
    private.mkdir(mode=0o700, exist_ok=True)
    with (private / 'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"status":"already_running"}')
            return 0
        state = State(private / 'weather.sqlite3')
        try:
            if args.status:
                print(json.dumps({'deliveries': state.db.execute(
                    'SELECT day,status,updated,message_id,error FROM deliveries ORDER BY day DESC LIMIT 7').fetchall()}))
                return 0
            # Late retries are useful only before the morning commute; never send yesterday's weather.
            if not (6 <= now.hour < 8 or (now.hour == 8 and now.minute <= 20)):
                print('{"status":"outside_delivery_window"}')
                return 0
            if state.get(now.date().isoformat()) in ('sent', 'sending', 'uncertain'):
                print('{"status":"already_handled"}')
                return 0
            try:
                text = collect(now)
            except Exception as exc:
                state.put(now.date().isoformat(), 'queued', now, error=type(exc).__name__)
                print(json.dumps({'status': 'source_unavailable', 'error_type': type(exc).__name__}))
                return 1
            try:
                qq = QQ()
                outcome = deliver(state, now, text, qq)
            except Exception as exc:
                state.put(now.date().isoformat(), 'queued', now, error=type(exc).__name__)
                outcome = 'queued'
            print(json.dumps({'status': outcome}))
            return 1 if outcome in ('queued', 'uncertain') else 0
        finally:
            state.db.close()


if __name__ == '__main__':
    raise SystemExit(main())
