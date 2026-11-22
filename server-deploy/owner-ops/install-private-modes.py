"""Install from a staging directory next to this script, preserving the live adapter."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

src = Path(__file__).resolve().parent
root = Path('/home/ubuntu/qq-dsh/codex-integration')
adapter = Path('/home/ubuntu/.dsh/profiles/web/node_modules/dsh-onebot-qq/lib/inbound.js').resolve()
profile = Path('/home/ubuntu/.dsh/profiles/web/cordis.patch.yml')
node = '/home/ubuntu/.local/node/bin/node'
backup = Path(tempfile.mkdtemp(prefix='before-private-modes-', dir=root))

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Live source differs at ' + old[:50])
    return text.replace(old, new)

def write(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(data)
    os.chmod(tmp.name, path.stat().st_mode if path.exists() else 0o600)
    os.replace(tmp.name, path)

inbound = adapter.read_text()
inbound = replace_once(inbound, "import {handleSmallcLogin}", """import {createPrivateRouter} from '/home/ubuntu/qq-dsh/codex-integration/private-modes.mjs';
import {callBroker} from '/home/ubuntu/qq-dsh/codex-integration/owner-tools.mjs';
const routePrivateMode = createPrivateRouter({
    broker: callBroker, loginIntent,
    login: (msg, ctx) => handleSmallcLogin(msg, ctx.selfId(), (action, data) => ctx.call(action, data))
});
import {loginIntent,handleSmallcLogin}""")
inbound = replace_once(inbound, """        if (await handleSmallcLogin(inbound, this.ctx.selfId(),
            (action,data) => this.ctx.call(action,data))) return;""", """        if (await routePrivateMode(inbound, this.ctx)) return;""")
config = replace_once(profile.read_text(), """          - id: qq-server-codex
            name: /home/ubuntu/qq-dsh/codex-integration/dafeiyu-codex.mjs
          - id: qq-owner-tools
            name: /home/ubuntu/qq-dsh/codex-integration/owner-tools.mjs""", """          - id: qq-daily-tools
            name: /home/ubuntu/qq-dsh/codex-integration/daily-tools.mjs""")
changes = {root / name: (src / name).read_bytes() for name in ('private-modes.mjs','daily-tools.mjs','gold-controls.mjs')}
changes.update({adapter:inbound.encode(), profile:config.encode()})
subprocess.run([node, '--test', str(src/'test-private-modes.mjs')], check=True)
for path in changes:
    if path.exists():
        shutil.copy2(path, backup/path.name)
service = ['sudo','-n','systemctl']
try:
    for path, data in changes.items():
        write(path, data)
    subprocess.run([node,'--check',str(adapter)], check=True)
    subprocess.run([node,'--input-type=module','-e',f"await import('{adapter}');await import('{root}/daily-tools.mjs')"], check=True)
    subprocess.run(service+['restart','deepseek-harness'],check=True)
    subprocess.run(service+['is-active','deepseek-harness','qq-owner-ops'],check=True)
except BaseException:
    for path in changes:
        original = backup/path.name
        if original.exists():
            write(path,original.read_bytes())
        elif path.exists():
            path.unlink()
    subprocess.run(service+['restart','deepseek-harness'],check=True)
    raise
print('Installed; backup:',backup)
