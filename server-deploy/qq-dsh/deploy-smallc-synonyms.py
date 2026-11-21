from pathlib import Path
from datetime import datetime,timezone
import shutil
import subprocess

ROOT=Path('/home/ubuntu/qq-dsh/smallc-login')
lib=Path('/home/ubuntu/.dsh/profiles/web/node_modules/dsh-onebot-qq').resolve()/'lib'
tools=Path('/home/ubuntu/qq-dsh/codex-integration/owner-tools.mjs')
notice=Path('/home/ubuntu/qq-codex/bridge/smallc_health_notice.py')
source=tools.read_text()
anchor=' registerReminders(ctx,defineTool,authorize);'
if source.count(anchor)!=1 or 'registerSmallcLogin' in source:raise RuntimeError('Owner tool entry changed/already installed')
updated="import {registerSmallcLogin} from '/home/ubuntu/.dsh/profiles/web/node_modules/dsh-onebot-qq/lib/smallc-relogin.mjs';\n"+source.replace(anchor,anchor+'\n registerSmallcLogin(ctx,defineTool,authorize);')
backup=ROOT/('backup-synonyms-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir(mode=0o700)
changes={lib/'smallc-relogin.mjs':(ROOT/'smallc-relogin.mjs').read_text(),tools:updated,notice:(ROOT/'smallc_health_notice.py').read_text()}
for n,p in enumerate(changes):shutil.copy2(p,backup/(str(n)+'-'+p.name))
try:
 for p,text in changes.items():p.write_text(text)
 subprocess.run(['/home/ubuntu/.local/node/bin/node','--check',str(tools)],check=True)
except BaseException:
 for n,p in enumerate(changes):shutil.copy2(backup/(str(n)+'-'+p.name),p)
 raise
print('Natural login intent and owner-only tool installed; backup='+str(backup))
