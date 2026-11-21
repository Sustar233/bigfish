"""Bounded real-model checks with synthetic messages; never send QQ messages."""
import concurrent.futures
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, '/home/ubuntu/qq-codex/bridge')
import bridge
from qq_data import approved_persona

original_run = bridge.run_metered


def limited_run(*args, **kwargs):
    kwargs['timeout'] = min(kwargs.get('timeout', 75), 75)
    kwargs['project'] = 'system_verification'
    return original_run(*args, **kwargs)


bridge.run_metered = limited_run
CASES = [
    ('joke', '帮我上班'),
    ('chat', '今天有点烦，先别给我列方案，就随便聊两句'),
    ('task', '请把下面这段工作汇报压成一句话：今天处理了3个登录问题；还有2个待排查；明天补回归测试。'),
]


def harness_reply(text, persona):
    prompt = (persona + '\n以下是用于验证聊天风格的模拟用户消息：\n'
              + json.dumps([{'role': 'user', 'content': text}], ensure_ascii=False)
              + '\n只输出本轮回复正文。')
    env = {k: v for k, v in os.environ.items()
           if not any(word in k.upper() for word in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY'))}
    env.update(HOME='/home/ubuntu', DSH_HOME='/home/ubuntu/.dsh',
               PATH='/home/ubuntu/.local/node/bin:/home/ubuntu/.local/share/pnpm:/usr/bin:/bin')
    process = subprocess.Popen(['/home/ubuntu/.local/share/pnpm/dsh', '--profile', 'qq-group', '-'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env, cwd='/home/ubuntu/qq-group/workspace', start_new_session=True)
    try:
        stdout, _ = process.communicate(prompt, timeout=75)
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    if process.returncode or not stdout.strip():
        raise RuntimeError('Harness generation failed')
    return stdout.strip()


def check(provider):
    directory = ('/home/ubuntu/qq-codex/bridge/.private/records' if provider == 'codex'
                 else '/home/ubuntu/qq-dsh/records')
    persona = approved_persona(Path(directory))
    if not persona:
        raise RuntimeError('Approved persona not loaded')
    rows = []
    for case, text in CASES:
        start = time.monotonic()
        try:
            reply = (bridge.model_reply([], text, persona=persona, search_query='') if provider == 'codex'
                     else harness_reply(text, persona))
            row = {'provider': provider, 'case': case, 'reply': reply[:2000],
                   'seconds': round(time.monotonic() - start, 1)}
            if case == 'task':
                row['facts_preserved'] = all(word in reply for word in ('3', '2', '明天', '回归'))
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        except Exception as exc:
            row = {'provider': provider, 'case': case, 'error': type(exc).__name__,
                   'seconds': round(time.monotonic() - start, 1)}
            rows.append(row)
            print(json.dumps(row), flush=True)
            break  # A failed provider is not retried or silently switched.
    return rows


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        result = sum(list(pool.map(check, ('codex', 'harness'))), [])
    (ROOT / 'smoke-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
