"""Apply small, backed-up patches to the current deployed bridges, preserving other edits."""
import ast
from datetime import datetime
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess

ROOT = Path('/home/ubuntu/server-maintenance/images')
PRIVATE = ROOT / '.private'
BRIDGE = Path('/home/ubuntu/qq-codex/bridge/bridge.py')
PLUGIN = Path('/home/ubuntu/.dsh/profiles/web/node_modules/dsh-onebot-qq/lib')
METER = Path('/home/ubuntu/server-maintenance/usage/usage_meter.py')


def main():
    originals = {p: p.read_bytes() for p in (BRIDGE, PLUGIN / 'inbound.js', METER)}
    updates = {p: raw.decode() for p, raw in originals.items()}
    if 'from image_commands import image_command' not in updates[BRIDGE]:
        anchor = '    def command(self, text, key):\n'
        assert updates[BRIDGE].count(anchor) == 1
        updates[BRIDGE] = updates[BRIDGE].replace(anchor, anchor +
            "        from image_commands import image_command\n"
            "        image_reply = image_command(text, key, str(self.config['bot_qq']))\n"
            "        if image_reply is not None:\n"
            "            return image_reply, None\n")
        anchor = "sys.path.insert(0, '/home/ubuntu/server-maintenance/usage')"
        assert updates[BRIDGE].count(anchor) == 1
        updates[BRIDGE] = updates[BRIDGE].replace(anchor, anchor +
            "\nsys.path.insert(0, '/home/ubuntu/server-maintenance/images')")
        updates[BRIDGE] = updates[BRIDGE].replace("/清空：新话题，保留档案", "生图：描述（一次一张）\\n/生图状态\\n/清空：新话题，保留档案")
    inbound = PLUGIN / 'inbound.js'
    if "from './codex-image.js'" not in updates[inbound]:
        updates[inbound] = "import { codexImageCommand } from './codex-image.js';\n" + updates[inbound]
        anchor = '        // Route commands before media/quote expansion.'
        assert updates[inbound].count(anchor) == 1
        seam = '''        // Explicit owner-only private image jobs bypass the DeepSeek model.
        if (kind === 'private' && userId === '1000000001'
            && this.ctx.selfId() === '1000000003' && inbound.messageId !== undefined
            && inbound.media.length === 0 && inbound.replyId === undefined && inbound.forwardId === undefined) {
            const reply = await codexImageCommand(inbound.text,
                `${inbound.time}/${inbound.messageId}`, '1000000003');
            if (reply !== null) {
                await this.ctx.sendToChat(chatId, reply);
                return;
            }
        }
'''
        updates[inbound] = updates[inbound].replace(anchor, seam + anchor)
    if "'qq_image_generation'" not in updates[METER]:
        anchor = 'PROJECTS = {\n'
        assert updates[METER].count(anchor) == 1
        updates[METER] = updates[METER].replace(anchor, anchor + " 'qq_image_generation': 'QQ生图（Codex）',\n")
    ast.parse(updates[BRIDGE])
    ast.parse(updates[METER])
    subprocess.run(['/home/ubuntu/.local/node/bin/node', '--input-type=module', '--check'],
        input=updates[inbound], text=True, capture_output=True, check=True)
    backup = PRIVATE / ('backup-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(mode=0o700)
    report = {}
    for p, body in updates.items():
        assert p.read_bytes() == originals[p], 'Source changed during patch; retry from current code'
        shutil.copy2(p, backup / p.name)
        if body != originals[p].decode():
            p.write_text(body)
        report[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    shutil.copy2(ROOT / 'codex-image.js', PLUGIN / 'codex-image.js')
    token = PRIVATE / 'client-token'
    if not token.exists():
        token.write_text(secrets.token_urlsafe(48))
    token.chmod(0o600)
    (PRIVATE / 'deployment.json').write_text(json.dumps({'backup': str(backup), 'hashes': report}, indent=2))
    print(json.dumps({'backup': str(backup), 'patched': len(updates)}))


if __name__ == '__main__':
    main()
