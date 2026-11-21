from datetime import datetime, timezone
from pathlib import Path
import ast
import shutil
import subprocess

ROOT=Path('/home/ubuntu/qq-reminders')
bridge=Path('/home/ubuntu/qq-codex/bridge/bridge.py')
tools=Path('/home/ubuntu/qq-dsh/codex-integration/owner-tools.mjs')
style=bridge.with_name('chat_style.md')
backup=ROOT/('backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
s=bridge.read_text();t=tools.read_text()
anchor="        if str(self.config.get('owner_qq')) == '1000000001':\n"
if s.count(anchor)!=1 or 'from reminder_client import private_command as reminder_command' in s:
    raise RuntimeError('Private entry changed or already installed')
new=s.replace(anchor,anchor+'''            from reminder_client import private_command as reminder_command
            reminder_reply = reminder_command(text, key, self.config['owner_qq'])
            if reminder_reply is not None:
                return reminder_reply, None
''')
ast.parse(new)
needle=" const {defineTool}=await import('@deepseek-ai/dsh-tools');"
if t.count(needle)!=1 or 'registerReminders' in t:raise RuntimeError('Owner tools entry changed or already installed')
t="import {registerReminders} from './reminder-tools.mjs';\n"+t.replace(needle,needle+'\n registerReminders(ctx,defineTool,authorize);')
changed={bridge:new,tools:t,style:style.read_text()+'''

## 本人授权的定时提醒
用户说“他们”默认指小c和肥鱼（大肥鱼）。服务器已接入持久定时提醒：本人私聊可说“半小时后提醒我喝水”“明天早上8点提醒我开会”“每天晚上8点提醒我看书”“工作日9:30给我发一句早安”，也可发 /提醒列表、/取消提醒 编号，或“取消刚才的提醒”。普通提醒不需要调用服务器执行工具，不建立额外cron。只有提醒服务的真实返回才能确认已设置；时间不明确先问，不能只口头答应。消息仅发给1000000001本人，由收到请求的本号发送。
'''}
for n,p in enumerate(changed):shutil.copy2(p,backup/(str(n)+'-'+p.name))
(ROOT/'backup-path.txt').write_text(str(backup))
shutil.copy2(ROOT/'reminder_client.py',bridge.parent/'reminder_client.py')
shutil.copy2(ROOT/'reminder-tools.mjs',tools.parent/'reminder-tools.mjs')
try:
    for p,data in changed.items():p.write_text(data)
    subprocess.run(['/home/ubuntu/.local/node/bin/node','--check',str(tools)],check=True)
except BaseException:
    for n,p in enumerate(changed):shutil.copy2(backup/(str(n)+'-'+p.name),p)
    raise
print('Reminder adapters installed; backup='+str(backup))
