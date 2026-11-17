"""Local generation comparison; never sends QQ messages or edits live chat history."""
import json, os, sys, subprocess, importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

BASE=Path('/home/ubuntu/qq-codex')
sys.path.insert(0,str(BASE/'bridge'))
backup=Path((BASE/'style-backup-path.txt').read_text().strip())
spec=importlib.util.spec_from_file_location('baseline_bridge',backup/'codex-bridge.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
style=(BASE/'chat_style.md').read_text()
cases={
 'joke':([], '帮我上班'),
 'context':([{'role':'user','content':'困了'},{'role':'assistant','content':'已经开始靠意志力睁眼了是吧。'}], '但我还要考试'),
}
env={k:v for k,v in os.environ.items() if not any(w in k.upper() for w in ('TOKEN','SECRET','PASSWORD','API_KEY'))}
env.update(HOME='/home/ubuntu',DSH_HOME='/home/ubuntu/.dsh',PATH='/home/ubuntu/.local/node/bin:/home/ubuntu/.local/share/pnpm:/usr/bin:/bin')

def test(provider):
 results=[]
 for version in ('before','after'):
  path=backup/('codex-persona.md' if provider=='codex' else 'harness-persona.md') if version=='before' else BASE/('codex-approved.md' if provider=='codex' else 'harness-approved.md')
  persona=path.read_text()+ ('\n'+style if version=='after' else '')
  for key,(history,message) in cases.items():
   try:
    if provider=='codex':reply=module.model_reply(history,message,persona=persona)
    else:
     prompt=persona+'\n以下是对话资料：\n'+json.dumps(history+[{'role':'user','content':message}],ensure_ascii=False)+'\n只输出本轮回复正文。'
     p=subprocess.run(['/home/ubuntu/.local/share/pnpm/dsh','--profile','qq-group','-'],input=prompt,capture_output=True,text=True,env=env,cwd='/home/ubuntu/qq-group/workspace',timeout=120)
     if p.returncode:raise RuntimeError('Harness generation failed')
     reply=p.stdout.strip()
    row={'provider':provider,'version':version,'case':key,'reply':reply[:2200]}
   except Exception as e:row={'provider':provider,'version':version,'case':key,'error':type(e).__name__}
   results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
 return results

with ThreadPoolExecutor(max_workers=2) as pool:
 rows=sum(list(pool.map(test,('codex','harness'))),[])
(BASE/'style-comparison-v3.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
