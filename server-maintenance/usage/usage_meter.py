"""Local usage ledger. Stores counts only, never prompts, replies or credentials."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path('/home/ubuntu/server-maintenance/usage/data')
TZ = timezone(timedelta(hours=8), 'Asia/Shanghai')
PROJECTS = {
 'deepseek_codex': '大肥鱼委托Codex',
 'qq_image_generation': 'QQ生图（Codex）',
 'gold_monitor': '金价监控', 'news_monitor': '新闻监控', 'zhihu_daily': '知乎日报',
 'qq_codex_private': '小c私聊', 'qq_codex_group': '小c群聊',
 'deepseek_private': 'DeepSeek私聊', 'deepseek_group': 'DeepSeek群聊',
 'system_verification': '系统验证', 'maintenance': '普通采集/备份/维护'}
ZERO = {'gold_monitor', 'maintenance'}


def connect():
    (ROOT/'.private').mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(ROOT/'.private/usage.sqlite3', timeout=20)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''CREATE TABLE IF NOT EXISTS calls(
      id TEXT PRIMARY KEY,at REAL,day TEXT,project TEXT,provider TEXT,status TEXT,
      input INTEGER,cached INTEGER,cache_write INTEGER,output INTEGER,reasoning INTEGER);
      CREATE TABLE IF NOT EXISTS imports(path TEXT PRIMARY KEY,signature TEXT);
      CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
    ''')
    return db


def normalized(usage, provider):
    def number(k):
        v = usage.get(k)
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0
    if provider == 'codex':
        return (number('input_tokens'), number('cached_input_tokens'), number('cache_write_input_tokens'),
                number('output_tokens'), number('reasoning_output_tokens'))
    output = number('outputTokens')
    cached, write = number('cacheReadTokens'), number('cacheWriteTokens')
    # Harness inputTokens excludes cache tokens; use the provider's total when present.
    total_input = number('totalTokens')-output if number('totalTokens') >= output and 'totalTokens' in usage else number('inputTokens')+cached+write
    return (total_input, cached, write, output, 0)


def record(project, provider, usage=None, status='ok', at=None, call_id=None):
    if os.environ.get('USAGE_METER_DISABLED') == '1':
        return
    at = time.time() if at is None else at
    counts = normalized(usage, provider) if usage is not None else (None,)*5
    with connect() as db:
        db.execute('INSERT OR IGNORE INTO calls VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (call_id or uuid.uuid4().hex, at, datetime.fromtimestamp(at,TZ).date().isoformat(), project, provider, status, *counts))
    db.close()


def parse_codex(stdout):
    totals = [0]*5
    seen = False
    for line in (stdout.decode('utf-8','replace') if isinstance(stdout,bytes) else stdout or '').splitlines():
        try:
            d=json.loads(line)
            if d.get('type') == 'turn.completed' and isinstance(d.get('usage'),dict):
                totals=[a+b for a,b in zip(totals,normalized(d['usage'],'codex'))]; seen=True
        except (ValueError,AttributeError):
            pass
    if not seen:
        return None
    return dict(zip(['input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens'],totals))


def run_metered(command, *, project, **kwargs):
    command=list(command)
    if '--json' not in command:
        command.insert(command.index('exec')+1,'--json')
    try:
        result=subprocess.run(command,**kwargs)
    except subprocess.TimeoutExpired as exc:
        save_safely(project,parse_codex(exc.stdout),'timeout')
        raise
    except OSError:
        save_safely(project,None,'launch_failed')
        raise
    save_safely(project,parse_codex(getattr(result,'stdout','')),'ok' if result.returncode == 0 else 'failed')
    return result


def save_safely(project,usage,status):
    if os.environ.get('USAGE_METER_DISABLED') == '1':
        return
    try:
        record(project,'codex',usage,status)
        export_reports()
    except Exception as exc:
        # Metering failures must not interrupt a conversation, alert, or daily delivery.
        print(json.dumps({'event':'usage_meter_unavailable','project':project,'error_type':type(exc).__name__}),file=sys.stderr)


def sync_harness():
    for scope,project in [('qq-dsh','deepseek_private'),('qq-group','deepseek_group')]:
        folder=Path('/home/ubuntu/.dsh/sessions')/('--home-ubuntu-'+scope+'-workspace--')
        for path in folder.rglob('*.jsonl.zstd'):
            stat=path.stat(); signature=f'{stat.st_size}:{stat.st_mtime_ns}'
            with connect() as db:
                row=db.execute('SELECT signature FROM imports WHERE path=?',(str(path),)).fetchone()
            db.close()
            if row and row[0] == signature:
                continue
            result=subprocess.run(['zstd','-dc',str(path)],capture_output=True,text=True,timeout=20)
            if result.returncode:
                continue
            for line in result.stdout.splitlines():
                try:
                    d=json.loads(line); data=d.get('data',{})
                    if d.get('type') != 'assistant/message' or not isinstance(data.get('usage'),dict):
                        continue
                    identity=hashlib.sha256((str(path)+':'+str(d['seq'])).encode()).hexdigest()
                    record(project,'deepseek',data['usage'],at=d['time']/1000,call_id=identity)
                except (ValueError,KeyError,TypeError):
                    continue
            with connect() as db:db.execute('INSERT OR REPLACE INTO imports VALUES(?,?)',(str(path),signature))
            db.close()


def atomic_write(path,text):
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8-sig' if path.suffix == '.csv' else 'utf-8',dir=path.parent,delete=False) as f:
        f.write(text); tmp=Path(f.name)
    tmp.chmod(0o600);tmp.replace(path)


def export_reports():
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (ROOT/'.export.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        db=connect()
        coverage=db.execute("SELECT value FROM meta WHERE key='coverage_start'").fetchone()
        coverage=float(coverage[0]) if coverage else time.time()
        rows=db.execute('''SELECT day,project,count(*),count(input),coalesce(sum(input),0),coalesce(sum(cached),0),
           coalesce(sum(output),0),coalesce(sum(cache_write),0),coalesce(sum(reasoning),0)
           FROM calls GROUP BY day,project ORDER BY day,project''').fetchall()
        db.close()
        grouped={(r[0],r[1]):r[2:] for r in rows}
        today=datetime.now(TZ).date(); first=min([datetime.fromisoformat(r[0]).date() for r in rows]+[today])
        out=ROOT/'daily';out.mkdir(mode=0o700,exist_ok=True)
        all_rows=[]
        while first<=today:
            date=first.isoformat(); items=[]
            for key,label in PROJECTS.items():
                calls,known,inp,cached,output,write,reasoning=grouped.get((date,key),(0,)*7)
                if key in ZERO: coverage_label='无模型调用'
                elif key.startswith('deepseek'):coverage_label='本地日志中已报告的用量'
                elif date<datetime.fromtimestamp(coverage,TZ).date().isoformat():coverage_label='历史未计量'
                elif date==datetime.fromtimestamp(coverage,TZ).date().isoformat():coverage_label='自'+datetime.fromtimestamp(coverage,TZ).strftime('%H:%M')+'起（此前未知）'
                else:coverage_label='已接入'
                unknown_history = coverage_label == '历史未计量' or (calls > 0 and known == 0)
                items.append([date,label,calls,'' if unknown_history else inp,'' if unknown_history else cached,
                              '' if unknown_history else output,'' if unknown_history else inp+output,calls-known,coverage_label])
            buffer=io.StringIO();writer=csv.writer(buffer)
            headers=['日期','项目','调用次数','输入token（含缓存）','缓存输入token（输入子集）','输出token','总token','usage缺失次数','记录范围']
            writer.writerow(headers);writer.writerows(items)
            atomic_write(out/(date+'.csv'),buffer.getvalue())
            md='# 每日项目 token 记录：'+date+'\n\n仅合计已返回的usage；缺失次数另列，历史未计量留空。输入已包含缓存输入，总量=输入+输出，缓存不重复相加。token用量不等于费用或订阅剩余额度。\n\n'
            md+='| 项目 | 调用次数 | 输入 | 缓存输入 | 输出 | 总量 | usage缺失 | 范围 |\n|---|---:|---:|---:|---:|---:|---:|---|\n'
            md+='\n'.join('| '+' | '.join(str(v) for v in r[1:])+' |' for r in items)+'\n'
            atomic_write(out/(date+'.md'),md)
            all_rows.extend(items);first+=timedelta(days=1)
        buffer=io.StringIO();writer=csv.writer(buffer);writer.writerow(headers);writer.writerows(all_rows)
        atomic_write(ROOT/'daily_totals.csv',buffer.getvalue())


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('--export',action='store_true');parser.add_argument('--sync-harness',action='store_true')
    args=parser.parse_args()
    if args.sync_harness:sync_harness()
    export_reports()
    print(json.dumps({'status':'usage_reports_updated','path':str(ROOT/'daily_totals.csv')}))
