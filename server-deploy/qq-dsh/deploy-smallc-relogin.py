"""Patch actual current sources, retaining other chat/media changes."""
from pathlib import Path
from datetime import datetime,timezone
import ast
import json
import shutil
import subprocess

ROOT=Path('/home/ubuntu/qq-dsh/smallc-login')
backup=ROOT/('backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
lib=Path('/home/ubuntu/.dsh/profiles/web/node_modules/dsh-onebot-qq').resolve()/'lib'
inbound=lib/'inbound.js'
maintenance=Path('/home/ubuntu/qq-codex/bridge/qq_maintenance.py')
s=inbound.read_text();m=maintenance.read_text()
anchor='        // Owner image/edit jobs: authenticated private attachments only.\n'
if s.count(anchor)!=1 or 'handleSmallcLogin' in s:raise RuntimeError('Inbound changed or already installed')
s="import {handleSmallcLogin} from './smallc-relogin.mjs';\n"+s.replace(anchor,'''        if (await handleSmallcLogin(inbound, this.ctx.selfId(),
            (action,data) => this.ctx.call(action,data))) return;
'''+anchor)
anchor='        if should_send:\n'
if m.count(anchor)!=1 or "from smallc_health_notice import notify" in m:raise RuntimeError('Health changed or already installed')
m=m.replace(anchor,'''        if should_send and label == 'codex' and onebot_health('harness', ACCOUNTS['harness'][0]) != 'ready':
            entry['qq_notification_pending'] = True
            should_send = False
        if should_send:
            entry['qq_notification_pending'] = False
''')
anchor='                mail(*health_notice(label, account, online))'
if m.count(anchor)!=1:raise RuntimeError('Health mail call changed')
m=m.replace(anchor,'''                if label == 'codex':
                    from smallc_health_notice import notify
                    notify(api, online)
                else:
                    mail(*health_notice(label, account, online))''')
ast.parse(m)
changes={inbound:s,maintenance:m}
for n,p in enumerate(changes):shutil.copy2(p,backup/(str(n)+'-'+p.name))
shutil.copy2(ROOT/'smallc-relogin.mjs',lib/'smallc-relogin.mjs')
shutil.copy2(ROOT/'smallc_health_notice.py',maintenance.parent/'smallc_health_notice.py')
try:
    for p,text in changes.items():p.write_text(text)
    subprocess.run(['/home/ubuntu/.local/node/bin/node','--check',str(inbound)],check=True)
except BaseException:
    for n,p in enumerate(changes):shutil.copy2(backup/(str(n)+'-'+p.name),p)
    raise
(ROOT/'deployment.json').write_text(json.dumps({'backup':str(backup),'files':[str(p) for p in changes],'owner':'1000000001','smallc_email_health_disabled':True,'qr_on_owner_request_only':True},indent=2))
print('Installed owner-only smallc relogin and QQ health notification; backup='+str(backup))
