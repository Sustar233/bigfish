"""Read-only production integration check. Does not install or restart anything."""
import ast
import hashlib
from pathlib import Path
import subprocess
import tempfile

from install import patched_sources


def main():
    paths = [Path('/home/ubuntu/qq-codex/bridge/bridge.py'),
             Path('/home/ubuntu/.dsh/profiles/web/node_modules/dsh-onebot-qq/lib/inbound.js').resolve(),
             Path('/home/ubuntu/qq-codex/bridge/group_chat.py')]
    originals = [path.read_text() for path in paths]
    modified = patched_sources(*originals)
    assert patched_sources(*modified) == modified, 'Patch must be idempotent'
    for index in (0, 2):
        ast.parse(modified[index])
    with tempfile.TemporaryDirectory() as temp:
        script = Path(temp)/'inbound.mjs'
        script.write_text(modified[1])
        subprocess.run(['/home/ubuntu/.local/node/bin/node','--check',str(script)],check=True)
    for path, old, new in zip(paths, originals, modified):
        print(path.name, 'anchor check OK;', 'added lines:', len(new.splitlines())-len(old.splitlines()),
              'source sha256:', hashlib.sha256(old.encode()).hexdigest()[:12])
    print('Read-only check passed. No live file, setting, or service was changed.')


if __name__ == '__main__':
    main()
