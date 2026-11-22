"""Run as root from a staged copy; patch only exact, verified live anchors."""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parent
ROOT = Path('/home/ubuntu/home-console')
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
BACKUP = ROOT / ('deploy-backups/' + STAMP)
CODE = ('app.py', 'control.py', 'index.html', 'style.css', 'app.js')


def patch(text, old, new):
    if new in text:
        return text
    if text.count(old) != 1:
        raise RuntimeError('Unexpected live source anchor: ' + old[:60])
    return text.replace(old, new, 1)


def patched_sources(smallc, harness, group):
    smallc = patch(smallc, '    def admit(self, event):\n',
        "    def admit(self, event):\n        if Path('/home/ubuntu/home-console/data/flags/smallc.paused').exists():\n            return False\n")
    smallc = patch(smallc, '                incoming = self.media_inputs.pop(key, {})\n',
        "                incoming = self.media_inputs.pop(key, {})\n                if Path('/home/ubuntu/home-console/data/flags/smallc.paused').exists():\n                    self.store.mark(key, 'home_paused')\n                    continue\n")
    smallc = patch(smallc, "                self.store.data.record(key+'/assistant', 'assistant', reply, status='generated')\n",
        "                if Path('/home/ubuntu/home-console/data/flags/smallc.paused').exists():\n                    self.store.mark(key, 'home_paused')\n                    continue\n                self.store.data.record(key+'/assistant', 'assistant', reply, status='generated')\n")
    harness = patch(harness, "    async processInbound(inbound) {\n", "    async processInbound(inbound) {\n        if (inbound.kind === 'private' && homePaused('/home/ubuntu/home-console/data/flags/harness.paused')) return;\n")
    if "import { existsSync as homePaused }" not in harness:
        harness = "import { existsSync as homePaused } from 'node:fs';\n" + harness
    group = patch(group, '    def admit(self, event):\n', "    def admit(self, event):\n        if Path('/home/ubuntu/home-console/data/flags/group.paused').exists():\n            return False\n")
    return smallc, harness, group


def unit(origin):
    return f'''[Unit]
Description=Private Bigfish home console
After=network.target deepseek-harness.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/home-console
Environment=HOME_ORIGIN={origin}
ExecStart=/usr/bin/python3 /home/ubuntu/home-console/app.py
Restart=on-failure
RestartSec=3
UMask=0077
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/ubuntu/home-console/data /home/ubuntu/qq-group/.private
PrivateTmp=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
MemoryMax=192M
TasksMax=40

[Install]
WantedBy=multi-user.target
'''


def main():
    import pwd
    if os.geteuid() != 0:
        raise SystemExit('Run using sudo python3 install.py')
    ROOT.mkdir(mode=0o755, exist_ok=True)
    BACKUP.mkdir(mode=0o700, parents=True)
    caddy = Path('/etc/caddy/Caddyfile')
    current = caddy.read_text()
    match = re.search(r'https://([\d.]+:\d+)\s*\{', current)
    if not match:
        raise RuntimeError('Existing HTTPS origin not found')
    origin = 'https://' + match[1]
    small = Path('/home/ubuntu/qq-codex/bridge/bridge.py')
    big = Path('/home/ubuntu/.dsh/profiles/web/node_modules/dsh-onebot-qq/lib/inbound.js').resolve()
    group = Path('/home/ubuntu/qq-codex/bridge/group_chat.py')
    s, h, g = patched_sources(small.read_text(), big.read_text(), group.read_text())
    compile(s, str(small), 'exec')
    compile(g, str(group), 'exec')
    check_js = BACKUP / 'inbound.mjs'
    check_js.write_text(h)
    subprocess.run(['/home/ubuntu/.local/node/bin/node', '--check', str(check_js)], check=True)
    route = '''\n\t# Bigfish private home; the application verifies the existing admin session.
\thandle /home {
\t\treverse_proxy 127.0.0.1:13220
\t}
\thandle /home/* {
\t\treverse_proxy 127.0.0.1:13220
\t}
'''
    if '# Bigfish private home;' not in current:
        anchor = '\n\tredir /'
        if current.count(anchor) != 1:
            raise RuntimeError('Unexpected public Caddy routes')
        current = current.replace(anchor, route + anchor, 1)
    candidate = BACKUP / 'Caddyfile.candidate'
    candidate.write_text(current)
    subprocess.run(['caddy', 'validate', '--config', str(candidate), '--adapter', 'caddyfile'], check=True, capture_output=True)
    owner = pwd.getpwnam('ubuntu')
    for folder in (ROOT, ROOT/'data', ROOT/'data/flags'):
        folder.mkdir(mode=0o700, exist_ok=True)
        os.chown(folder, owner.pw_uid, owner.pw_gid)
    # The executable privileged helper and its source are root-owned.
    helper = Path('/usr/local/sbin/bigfish-home-timer')
    privileged = Path('/usr/local/lib/bigfish-home-control.py')
    sudoers = Path('/etc/sudoers.d/bigfish-home')
    login = next((path for path in (
        SOURCE / 'smallc_login.py',
        SOURCE.parent.parent / 'server-maintenance/smallc_login.py',
        Path('/home/ubuntu/server-maintenance/smallc_login.py'),
    ) if path.is_file()), None)
    if login is None:
        raise RuntimeError('Existing smallc login helper is missing')
    changes = {ROOT/name: (SOURCE/name).read_bytes() for name in CODE}
    changes.update({ROOT/'smallc_login.py': login.read_bytes(), small:s.encode(), big:h.encode(), group:g.encode(),
        caddy:current.encode(), Path('/etc/systemd/system/bigfish-home.service'):unit(origin).encode(),
        privileged:(SOURCE/'control.py').read_bytes(),
        helper:b'#!/bin/sh\nexec /usr/bin/python3 -I /usr/local/lib/bigfish-home-control.py "$@"\n',
        sudoers:b'ubuntu ALL=(root) NOPASSWD: /usr/local/sbin/bigfish-home-timer *\n'})
    public = Path('/srv/personal-page/index.html')
    if public.exists() and '/home/">小家' not in public.read_text():
        html = public.read_text()
        anchor = '<nav aria-label="主导航">'
        if html.count(anchor) != 1:
            raise RuntimeError('Unexpected personal page navigation')
        changes[public] = html.replace(anchor, anchor+f'<a href="{origin}/home/">小家</a>', 1).encode()
    paths = {}
    for index, path in enumerate(changes):
        if path.exists():
            saved = BACKUP / str(index)
            shutil.copy2(path, saved)
            paths[str(path)] = str(saved)
        else:
            paths[str(path)] = None
    (BACKUP/'manifest.json').write_text(__import__('json').dumps(paths, indent=2))
    def write(path, data):
        # Preserve the owner and mode of existing live files.
        stat = path.stat() if path.exists() else None
        fd, name = tempfile.mkstemp(dir=path.parent)
        with os.fdopen(fd, 'wb') as file:
            file.write(data)
        os.chmod(name, stat.st_mode & 0o777 if stat else 0o644)
        if stat:
            os.chown(name, stat.st_uid, stat.st_gid)
        os.replace(name, path)
    try:
        for path, data in changes.items():
            write(path, data)
        for name in (*CODE, 'smallc_login.py'):
            os.chown(ROOT/name, owner.pw_uid, owner.pw_gid)
        helper.chmod(0o755)
        sudoers.chmod(0o440)
        subprocess.run(['visudo', '-cf', str(sudoers)], check=True, capture_output=True)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', '--now', 'bigfish-home.service'], check=True)
        subprocess.run(['systemctl', 'restart', 'qq-chat', 'qq-group', 'deepseek-harness', 'caddy'], check=True)
        subprocess.run(['systemctl', 'is-active', 'bigfish-home', 'qq-chat', 'qq-group', 'deepseek-harness', 'caddy'], check=True)
    except BaseException:
        for target, saved in paths.items():
            if saved:
                shutil.copy2(saved, target)
            else:
                Path(target).unlink(missing_ok=True)
        subprocess.run(['systemctl', 'daemon-reload'])
        subprocess.run(['systemctl', 'stop', 'bigfish-home'])
        subprocess.run(['systemctl', 'restart', 'qq-chat', 'qq-group', 'deepseek-harness', 'caddy'])
        raise
    print('Published:', origin+'/home/')
    print('Backup:', BACKUP)


if __name__ == '__main__':
    main()
