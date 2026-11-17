"""Install the static personal page without changing existing HTTPS routes."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess

config = Path('/etc/caddy/Caddyfile')
original = config.read_text()
empty = 'http://43.142.167.150 {\n}'
configured = '''http://43.142.167.150 {
\troot * /srv/personal-page
\tencode zstd gzip
\theader X-Content-Type-Options nosniff
\theader Referrer-Policy strict-origin-when-cross-origin
\tfile_server
}'''
if empty not in original and configured not in original:
    raise SystemExit('HTTP block changed; refusing to replace unrelated configuration.')
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = config.with_name('Caddyfile.before-personal-page.' + stamp)
shutil.copy2(config, backup)
root = Path('/srv/personal-page')
root.mkdir(mode=0o755, exist_ok=True)
page = root / 'index.html'
if page.exists():
    shutil.copy2(page, root / ('index.html.backup.' + stamp))
    # Keep backups outside the publicly served directory.
    shutil.move(str(root / ('index.html.backup.' + stamp)), '/home/ubuntu/personal-page/index.html.backup.' + stamp)
pending = root / '.index.pending'
shutil.copyfile('/home/ubuntu/personal-page/index.html', pending)
pending.chmod(0o644)
pending.replace(page)
candidate = config.with_name('Caddyfile.personal-page.pending')
candidate.write_text(original.replace(empty, configured, 1))
try:
    subprocess.run(['caddy', 'validate', '--config', str(candidate), '--adapter', 'caddyfile'], check=True)
    candidate.replace(config)
    subprocess.run(['systemctl', 'restart', 'caddy'], check=True)
    subprocess.run(['curl', '--fail', '--silent', '--show-error', '-H', 'Host: 43.142.167.150', 'http://127.0.0.1/', '-o', '/dev/null'], check=True)
except Exception:
    shutil.copy2(backup, config)
    subprocess.run(['systemctl', 'restart', 'caddy'], check=False)
    raise
print('Personal page installed; Caddy configuration backup:', backup)
