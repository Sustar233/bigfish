"""Read-only server feature overview; never prints credentials or chat content."""
import json
from pathlib import Path
import sqlite3
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parent


def main():
    registry = json.loads((ROOT/'services.json').read_text())
    result = {'server': registry['server'], 'timezone': registry['timezone'], 'features': []}
    for feature in registry['features']:
        units = []
        for unit in feature['units']:
            r = subprocess.run(['systemctl','show',unit,'-p','Id','-p','LoadState','-p','ActiveState',
                '-p','SubState','-p','Result','-p','ExecMainStatus','-p','NextElapseUSecRealtime'],capture_output=True,text=True)
            units.append(dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line))
        result['features'].append({'id':feature['id'],'name':feature['name'],'root':feature['root'],'units':units})
    result['qq_accounts'] = []
    for label,path,port in [
        ('小c','/home/ubuntu/qq-codex/bridge/.private/config.json',13001),
        ('DeepSeek','/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json',13101)]:
        try:
            config=json.loads(Path(path).read_text())
            request=urllib.request.Request(f'http://127.0.0.1:{port}/get_status',headers={'Authorization':'Bearer '+config['onebot_token']})
            op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with op.open(request,timeout=6) as response: data=json.load(response).get('data',{})
            result['qq_accounts'].append({'name':label,'online':data.get('online'),'good':data.get('good')})
        except Exception as exc: result['qq_accounts'].append({'name':label,'error_type':type(exc).__name__})
    result['monitor_summary']={}
    for label,path in [('gold','/home/ubuntu/gold-watch/.private/state.sqlite3'),('news',str(ROOT/'news/.private/news.sqlite3'))]:
        try:
            with sqlite3.connect('file:'+path+'?mode=ro',uri=True) as db:
                data={k:json.loads(v) for k,v in db.execute('SELECT key,value FROM state')}
            allowed=['last_check','last_error','zone'] if label=='gold' else ['last_collection','source_health','last_editor_failed','last_editor_error','last_digest_error']
            result['monitor_summary'][label]={k:data[k] for k in allowed if k in data}
        except Exception as exc:result['monitor_summary'][label]={'error_type':type(exc).__name__}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
