"""Bounded archiving, encrypted backups and metadata-only email health alerts."""
import argparse
import base64
import ctypes
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import smtplib
import sqlite3
import ssl
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from email.message import EmailMessage
from qq_data import Data, TZ
from datetime import datetime

ROOT = Path('/home/ubuntu/qq-memory')
ACCOUNTS = {'codex': ('1000000002', Path('/home/ubuntu/qq-codex/bridge/.private/records'),
                       Path('/home/ubuntu/qq-codex/bridge/.private/config.json')),
            'harness': ('1000000003', Path('/home/ubuntu/qq-dsh/records'),
                        Path('/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json'))}


def api(label, action, body=None):
    cfg = json.loads(ACCOUNTS[label][2].read_text())
    req = urllib.request.Request(cfg['onebot_url']+'/'+action, data=json.dumps(body or {}).encode(),
        headers={'Authorization':'Bearer '+cfg['onebot_token'], 'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=8) as response:
        result = json.load(response)
    if result.get('status') != 'ok':
        raise RuntimeError('OneBot request failed')
    return result.get('data')


def frames(content, start=0):
    lib = ctypes.CDLL('libzstd.so.1')
    for name in ('ZSTD_findFrameCompressedSize', 'ZSTD_getFrameContentSize'):
        f = getattr(lib, name); f.argtypes = [ctypes.c_void_p, ctypes.c_size_t]; f.restype = ctypes.c_ulonglong
    lib.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    lib.ZSTD_decompress.restype = ctypes.c_size_t
    pos = start
    buffer = ctypes.create_string_buffer(content)
    while pos < len(content):
        part = ctypes.byref(buffer, pos)
        size = lib.ZSTD_findFrameCompressedSize(part, len(content)-pos)
        if not size or size > len(content)-pos:
            break  # writer may still be appending its last frame
        outsize = lib.ZSTD_getFrameContentSize(part, size)
        if outsize > 8*1024*1024:
            outsize = 8*1024*1024
        out = ctypes.create_string_buffer(outsize)
        got = lib.ZSTD_decompress(out, outsize, part, size)
        if got > outsize:
            raise ValueError('Session decompression failed')
        pos += size
        yield pos, out.raw[:got].decode('utf-8')


def session_messages(record):
    """Export visible chat only; omit model reasoning, system prompts and tools."""
    kind = record.get('type')
    data = record.get('data', {})
    if kind == 'user/message':
        message = data
        if message.get('source', {}).get('kind') != 'plugin:dsh-onebot':
            return None
    elif kind == 'assistant/message':
        message = data.get('message', {})
    else:
        return None
    segments = [s for s in message.get('content', []) if s.get('type') in ('text', 'image', 'file', 'audio')]
    text = '\n'.join(s.get('text', '') for s in segments if s.get('type') == 'text')
    if not text and not segments:
        return None
    return message.get('id'), message.get('role'), text, segments


def collect_harness():
    account, directory, _ = ACCOUNTS['harness']
    store = Data(directory, account)
    try:
        root = Path('/home/ubuntu/.dsh/sessions/--home-ubuntu-qq-dsh-workspace--')
        for path in root.rglob('session.v4.jsonl.zstd'):
            if 'onebot-private-1000000001' not in str(path):
                continue
            marker = 'source:'+str(path)
            stamp = str(path.stat().st_mtime_ns)
            previous = store.db.execute('SELECT value FROM metadata WHERE key=?', (marker,)).fetchone()
            saved = json.loads(previous[0]) if previous else {}
            if saved.get('stamp') == stamp:
                continue
            raw = path.read_bytes()
            fingerprint = hashlib.sha256(raw[:128]).hexdigest()
            offset = saved.get('offset', 0) if saved.get('fingerprint') == fingerprint else 0
            if offset > len(raw):
                offset = 0
            for offset, frame in frames(raw, offset):
                for line in frame.splitlines():
                    record = json.loads(line)
                    value = session_messages(record)
                    if not value:
                        continue
                    mid, role, text, segments = value
                    key = 'harness-session/'+hashlib.sha256((str(path)+'/'+str(mid)).encode()).hexdigest()
                    stamp_ms = record.get('time', 0)
                    stamp_s = stamp_ms/1000 if stamp_ms > 100000000000 else stamp_ms
                    store.record(key, role, text, occurred=stamp_s or time.time(), status='engine_recorded',
                        source='harness-session', payload={'segments': segments, 'seq': record.get('seq')})
            with store.db:
                store.db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (marker,
                    json.dumps({'stamp': stamp, 'offset': offset, 'fingerprint': fingerprint})))
        store.publish_memories()
    finally:
        store.close()


def mail(subject, body):
    values = {}
    path = Path('/home/ubuntu/dailyZhihu/.private/server.env')
    if path.stat().st_mode & 0o077:
        raise PermissionError('Unsafe SMTP config permissions')
    for line in path.read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and key.startswith('SMTP_'):
            values[key] = value.strip()
    msg = EmailMessage()
    sender = values.get('SMTP_FROM') or values['SMTP_USER']
    msg['From'], msg['To'], msg['Subject'] = sender, 'owner@example.com', subject
    msg.set_content(body)
    port = int(values.get('SMTP_PORT', '465'))
    if port != 465:
        raise ValueError('Expected configured TLS SMTP')
    with smtplib.SMTP_SSL(values['SMTP_HOST'], port, timeout=30, context=ssl.create_default_context()) as smtp:
        smtp.login(values['SMTP_USER'], values['SMTP_PASSWORD'])
        smtp.send_message(msg)


def onebot_health(label, account):
    try:
        status = api(label, 'get_status')
        if status.get('online') is not True:
            return 'offline'
        if status.get('good') is not True:
            return 'degraded'
        if str(api(label, 'get_login_info').get('user_id')) != str(account):
            return 'account_mismatch'
    except Exception:
        return 'unavailable'
    return 'ready'


def health():
    path = ROOT/'health.json'
    state = json.loads(path.read_text()) if path.exists() else {}
    now = time.time()
    for label, (account, _, _) in ACCOUNTS.items():
        onebot_state = onebot_health(label, account)
        online = onebot_state == 'ready'
        old = state.get(label, {})
        failures = 0 if online else old.get('failures', 0)+1
        if label == 'codex':
            try:
                from reconnect_push import heartbeat as recovery_heartbeat
                recovery_heartbeat(online)
            except Exception as exc:
                print(json.dumps({'event':'reconnect_catchup_failed','error_type':type(exc).__name__}))
        sent = old.get('alerted_at', 0)
        changed = old.get('alert_active', False)
        should_send = (not online and failures >= 2 and now-sent > 6*3600) or (online and changed)
        if label == 'codex':
            outage = onebot_state == 'offline' or failures >= 2
            should_send = (not online and outage and not old.get('offer_sent')) or (online and changed)
        entry = {'online': online, 'onebot_state': onebot_state, 'failures': failures, 'checked_at': now,
                 'alerted_at': sent, 'alert_active': changed}
        if label == 'codex':
            entry['offer_sent'] = bool(old.get('offer_sent')) and not online
        if should_send and label == 'codex' and onebot_health('harness', ACCOUNTS['harness'][0]) != 'ready':
            entry['qq_notification_pending'] = True
            should_send = False
        if should_send:
            entry['qq_notification_pending'] = False
            # Reserve before delivery: an uncertain outcome must not spam.
            entry.update(alerted_at=now, alert_active=not online)
            state[label] = entry
            path.write_text(json.dumps(state))
            try:
                if label == 'codex':
                    from smallc_health_notice import notify
                    notify(api, online)
                    entry['offer_sent'] = not online
                else:
                    mail(f'[QQ 助手{"已恢复" if online else "离线"}] {label} {account}',
                        f'账号 {account}：'+('已恢复在线。' if online else '连续两次检查不可用，可能需要手机 QQ 重新验证。')+
                        '\n这里只报告服务状态，不附聊天正文、二维码或令牌。')
            except Exception as exc:
                if label == 'codex':
                    entry['alert_active'] = changed
                print(json.dumps({'event':'health_mail_failed','error_type':type(exc).__name__}))
        state[label] = entry
    logs = subprocess.check_output(['journalctl','-u','qq-chat.service','--since','10 minutes ago','--no-pager','-o','cat'], text=True)
    failures = [json.loads(line) for line in logs.splitlines() if line.startswith('{') and '"event": "model_failed"' in line]
    if failures and now-state.get('model_alerted_at', 0)>6*3600:
        state['model_alerted_at'] = now
        path.write_text(json.dumps(state))
        try:
            mail('[QQ Codex 模型调用异常]', '最近生成失败分类：'+str(failures[-1].get('category','generation'))+
                 '。请检查模型登录、额度或代理；没有发送聊天内容。')
        except Exception as exc:
            print(json.dumps({'event':'model_mail_failed','error_type':type(exc).__name__}))
    path.write_text(json.dumps(state, indent=2))


def encrypt(payload, public_pem):
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    public = serialization.load_pem_public_key(public_pem)
    key, nonce = os.urandom(32), os.urandom(12)
    wrapped = public.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    ciphertext = AESGCM(key).encrypt(nonce, payload, b'QQ-PRIVATE-BACKUP-v1')
    return json.dumps({'version':1,'algorithm':'RSA-OAEP-SHA256/AES-256-GCM',
        'wrapped_key':base64.b64encode(wrapped).decode(), 'nonce':base64.b64encode(nonce).decode(),
        'ciphertext':base64.b64encode(ciphertext).decode()}).encode()


def backup():
    out = ROOT/'backups';out.mkdir(mode=0o700,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='qq-backup-') as temporary:
        temp = Path(temporary)
        for label, (account, directory, _) in ACCOUNTS.items():
            store = Data(directory, account)
            try:
                store.snapshot(temp/(label+'.sqlite3'))
                for name in ('USER_MEMORY.md','persona.md','persona-approved.json'):
                    src = directory/name
                    if src.exists():
                        (temp/(label+'-'+name)).write_bytes(src.read_bytes())
            finally:
                store.close()
        group_root=Path('/home/ubuntu/qq-group/records')
        if (group_root/'archive.sqlite3').exists():
            store=Data(group_root,'1000000004')
            try:
                store.snapshot(temp/'group.sqlite3')
                if (group_root/'USER_MEMORY.md').exists():
                    (temp/'group-USER_MEMORY.md').write_bytes((group_root/'USER_MEMORY.md').read_bytes())
            finally:store.close()
            control=Path('/home/ubuntu/qq-group/.private/control.sqlite3')
            if control.exists():
                import sqlite3
                with sqlite3.connect(control) as src,sqlite3.connect(temp/'group-control.sqlite3') as dst:
                    src.backup(dst)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
            for path in temp.iterdir():
                archive.add(path,arcname=path.name)
        data = encrypt(buffer.getvalue(), (ROOT/'backup-public.pem').read_bytes())
    path = out/(datetime.now(TZ).strftime('%Y%m%d-%H%M%S')+'.qqbak')
    path.write_bytes(data);path.chmod(0o600)
    for old in out.glob('*.qqbak'):
        if old.stat().st_mtime<time.time()-30*86400:
            old.unlink()
    print(json.dumps({'event':'encrypted_backup_saved','file':path.name,'bytes':len(data)}))


if __name__ == '__main__':
    os.umask(0o077)
    ROOT.mkdir(mode=0o700,exist_ok=True)
    parser=argparse.ArgumentParser();parser.add_argument('--backup',action='store_true');parser.add_argument('--collect-only',action='store_true');args=parser.parse_args()
    collect_harness()
    if args.backup:
        backup()
    elif not args.collect_only:
        health()
