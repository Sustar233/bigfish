"""Install owner-scoped execution adapters against the actual live files."""
import base64
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/home/ubuntu/qq-owner-ops')
BACKUP = ROOT / ('backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
BACKUP.mkdir(mode=0o700)
targets = [Path('/home/ubuntu/qq-codex/bridge/bridge.py'),
           Path('/home/ubuntu/qq-dsh/codex-integration/dafeiyu-codex.mjs'),
           Path('/home/ubuntu/.dsh/profiles/web/cordis.patch.yml')]
for index, path in enumerate(targets):
    shutil.copy2(path, BACKUP / (str(index) + '-' + path.name))
(ROOT / 'backup-path.txt').write_text(str(BACKUP))

profile = Path('/home/ubuntu/.dsh/profiles/qq-owner')
if profile.exists():
    raise RuntimeError('Owner profile already exists; refusing to replace')
shutil.copytree('/home/ubuntu/.dsh/profiles/qq-group', profile)
(Path('/home/ubuntu/.dsh/sessions')).mkdir(exist_ok=True, mode=0o700)

node = r'''
import fs from 'node:fs'; import {createRequire} from 'node:module';
const r='/home/ubuntu/.local/share/dsh-runtime/node_modules/.pnpm';const f=fs.readdirSync(r).find(x=>x.startsWith('yaml@'));
const yaml=createRequire(import.meta.url)(r+'/'+f+'/node_modules/yaml');
let p='/home/ubuntu/.dsh/profiles/qq-owner/cordis.patch.yml';let a=yaml.parse(fs.readFileSync(p,'utf8'));
for(const e of a){if(['tool-bash','tool-fs','tool-fs-search','tool-jobs','tool-working-directory'].includes(e.id))e.disabled=false;
 if(e.id==='system-prompt')e.config.personaPrefix='你是1000000001本人私聊授权的服务器执行器。按本次明确任务检查、修改和验证项目。只报告实际结果，不改身份、权限或认证，不发送消息或调用其他模型。';}
fs.writeFileSync(p,yaml.stringify(a));fs.chmodSync(p,0o600);
p='/home/ubuntu/.dsh/profiles/web/cordis.patch.yml';a=yaml.parse(fs.readFileSync(p,'utf8'));
let preset=a.flatMap(e=>e.insert??[]).find(e=>e.id==='qq-natural-preset');
if(!preset)throw Error('Scoped QQ preset not found');
if(preset.config.plugins.some(e=>e.id==='qq-owner-tools'))throw Error('Already installed');
preset.config.plugins.push({id:'qq-owner-tools',name:'/home/ubuntu/qq-dsh/codex-integration/owner-tools.mjs'});
fs.writeFileSync(p,yaml.stringify(a));fs.chmodSync(p,0o600);
'''
subprocess.run(['/home/ubuntu/.local/node/bin/node', '--input-type=module', '-'], input=node, text=True, check=True)

path=targets[1]
text=path.read_text()
start=text.index('export async function dispatch(')
end=text.index('export async function apply(ctx)',start)
text="import {callBroker} from './owner-tools.mjs';\n"+text[:start]+'''export async function dispatch(args, exec) {
  authorize(exec);
  return callBroker(args, exec, 'codex');
}

'''+text[end:]
text=text.replace('专用工作目录编写文件选workspace_write', '修改服务器项目选workspace_write')
text=text.replace('专用工作目录编写文件', '已授权服务器项目编写文件')
text=text.replace('只读检查选read_only，专用工作目录编写文件选workspace_write。', '可检查、修改已授权服务器项目。')
text=text.replace('长任务自动回传。', '长任务用任务编号查询。')
text=text.replace('长任务说明已提交及任务编号，完成后程序自动回传，不要频繁查询。', '长任务说明已提交及编号，用户可查询实际结果或取消。')
text=text.replace('你没有通用服务器终端或sudo；受限路径的修改请提供方案。', '执行器可修改既有服务器项目，无root权限；系统与认证修改另行处理。')
path.write_text(text);path.chmod(0o600)
shutil.copy2(ROOT/'owner-tools.mjs',path.parent/'owner-tools.mjs')
shutil.copy2(ROOT/'client.py',targets[0].parent/'owner_client.py')
text=targets[0].read_text()
match=re.search(r'^    def command\(self, text, key[^\n]*\):\n',text,re.M)
if not match:raise RuntimeError('Private command anchor mismatch')
anchor=match.group(0)
addition='''        if str(self.config.get('owner_qq')) == '1000000001':
            from owner_client import private_command
            operation_reply = private_command(text, key, self.config['owner_qq'])
            if operation_reply is not None:
                return operation_reply, None
'''
targets[0].write_text(text.replace(anchor,anchor+addition))
subprocess.run(['python3','-m','py_compile',str(targets[0]),str(ROOT/'broker.py')],check=True)
subprocess.run(['/home/ubuntu/.local/node/bin/node','--check',str(path)],check=True)
print(json.dumps({'backup':str(BACKUP),'profile':'qq-owner','owner_private_only':True}))
