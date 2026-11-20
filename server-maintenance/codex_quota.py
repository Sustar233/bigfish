"""Read Codex subscription limits without starting a model turn."""
import json
import os
import selectors
import signal
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')


def read_limits(timeout=45):
    process = subprocess.Popen(
        ['codex', 'app-server', '--stdio'], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)

    def send(message):
        process.stdin.write((json.dumps(message) + '\n').encode())
        process.stdin.flush()

    try:
        send({'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'server_maintenance', 'version': '1.0.0'}}})
        deadline = time.monotonic() + timeout
        pending = b''
        while time.monotonic() < deadline:
            if b'\n' not in pending:
                if not selector.select(max(0, deadline - time.monotonic())):
                    break
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError('Codex app-server closed before returning limits')
                pending += chunk
                continue
            line, pending = pending.split(b'\n', 1)
            message = json.loads(line)
            if message.get('id') not in (1, 2):
                continue
            if 'error' in message:
                # Do not expose arbitrary server errors, which can contain URLs.
                raise RuntimeError('Codex quota query failed; code=' +
                                   str(message['error'].get('code')))
            if message['id'] == 1:
                send({'method': 'initialized', 'params': {}})
                send({'id': 2, 'method': 'account/rateLimits/read'})
            else:
                return message['result']
        raise TimeoutError('Codex quota query timed out')
    finally:
        selector.close()
        process.stdin.close()
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        process.stdout.close()


def summarize(result):
    buckets = result.get('rateLimitsByLimitId') or {'codex': result.get('rateLimits')}
    output = {'checked_at': datetime.now(TZ).isoformat(), 'timezone': 'Asia/Shanghai',
              'buckets': []}
    for identifier, bucket in buckets.items():
        if not bucket:
            continue
        entry = {'limit_id': identifier, 'windows': []}
        for key in ('primary', 'secondary'):
            window = bucket.get(key)
            if window:
                reset = window.get('resetsAt')
                entry['windows'].append({
                    'window': key, 'duration_minutes': window.get('windowDurationMins'),
                    'used_percent': window.get('usedPercent'),
                    'resets_at': datetime.fromtimestamp(reset, TZ).isoformat()
                    if reset is not None else None,
                })
        output['buckets'].append(entry)
    return output


if __name__ == '__main__':
    try:
        print(json.dumps(summarize(read_limits()), ensure_ascii=False, indent=2))
    except (RuntimeError, TimeoutError, OSError) as exc:
        print(json.dumps({'status': 'unavailable', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
