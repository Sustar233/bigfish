"""Meter backup traffic, prefer the original proxy, and leave unmatched traffic direct."""
from datetime import datetime, timezone, timedelta
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path('/home/ubuntu/server-maintenance/network')
CONFIG = Path('/home/ubuntu/.config/codex-proxy/config.json')
XRAY = '/home/ubuntu/.local/share/codex-proxy/xray'
TZ = timezone(timedelta(hours=8), 'Asia/Shanghai')


def account(previous, total, today, generation=None):
    used = previous.get('used', 0) if previous.get('day') == today else 0
    old = previous.get('last_counter', 0)
    reset = generation is not None and generation != previous.get('generation')
    delta = total if reset or total < old else total - old
    return {'day': today, 'used': used + max(0, delta), 'last_counter': total,
            'generation': generation}


def choose(primary_ok, stats_ok, used, policy):
    limit = policy.get('daily_backup_limit_bytes')
    capped = limit is not None and used >= max(0, limit - policy.get('stop_margin_bytes', 2097152))
    if primary_ok:
        return 'original', capped
    return ('backup' if stats_ok and not capped else 'blocked'), capped


def atomic(path, data, owner=None):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
        tmp = Path(f.name)
    tmp.chmod(0o600)
    if owner:
        os.chown(tmp, *owner)
    tmp.replace(path)


def command(args, timeout=10):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True).stdout


def primary_healthy():
    try:
        for url, accepted in [('https://www.gstatic.com/generate_204', {'204'}),
                              ('https://chatgpt.com/backend-api/codex/models', {'200', '401'})]:
            code = command(['curl', '-sS', '-o', '/dev/null', '--max-time', '6',
                        '--connect-timeout', '4', '--noproxy', '', '-x',
                        'http://127.0.0.1:17890', '-w', '%{http_code}',
                        url], 8).strip()
            if code not in accepted:
                return False
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def statistics():
    generation = command(['systemctl', 'show', 'codex-proxy.service', '-p', 'InvocationID', '--value']).strip()
    result = json.loads(command([XRAY, 'api', 'statsquery', '--server=127.0.0.1:17895',
                                '-pattern', 'outbound>>>backup'], 8))
    total = sum(int(v.get('value', 0)) for v in result.get('stat', [])
                if v.get('name', '').startswith(('outbound>>>backup_ai>>>traffic>>>',
                                                  'outbound>>>backup_web>>>traffic>>>',
                                                  'outbound>>>backup_gold>>>traffic>>>')))
    return total, generation


def main():
    with (ROOT / '.private/guard.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        policy = json.loads((ROOT / 'policy.json').read_text())
        path = ROOT / '.private/traffic_state.json'
        prior = json.loads(path.read_text()) if path.exists() else {}
        now = datetime.now(TZ)
        stats_ok = True
        try:
            total, generation = statistics()
            state = account(prior, total, now.date().isoformat(), generation)
        except (subprocess.SubprocessError, OSError, ValueError, KeyError):
            stats_ok = False
            state = dict(prior)
            state.setdefault('used', 0)
        healthy = primary_healthy()
        mode, capped = choose(healthy, stats_ok, state['used'], policy)
        config = json.loads(CONFIG.read_text())
        changed = False
        groups = {'restricted-ai': 'backup_ai', 'restricted-web': 'backup_web',
                  'restricted-gold': 'backup_gold'}
        for rule in config['routing']['rules']:
            key = rule.get('ruleTag')
            if key in groups:
                tag = groups[key] if mode == 'backup' else mode
                if rule['outboundTag'] != tag:
                    rule['outboundTag'] = tag
                    changed = True
        if changed:
            original_stat = CONFIG.stat()
            atomic(CONFIG, config, (original_stat.st_uid, original_stat.st_gid))
            command([XRAY, 'run', '-test', '-config', str(CONFIG)])
            command(['systemctl', 'restart', 'codex-proxy.service'], 15)
            state['generation'] = command(['systemctl', 'show', 'codex-proxy.service', '-p', 'InvocationID', '--value']).strip()
            state['last_counter'] = 0
        state.update(checked_at=now.isoformat(timespec='seconds'), primary_healthy=healthy,
                     stats_ok=stats_ok, backup_blocked=capped or not stats_ok,
                     daily_limit=policy.get('daily_backup_limit_bytes'), selected_route=mode)
        atomic(path, state)
        atomic(ROOT / 'status.json', state)
        print(json.dumps(state, ensure_ascii=False))


if __name__ == '__main__':
    main()
