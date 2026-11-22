"""Route only smallc health transitions to the owner's whale QQ account."""
OWNER='1000000001'


from pathlib import Path
import time

PENDING = Path('/home/ubuntu/qq-codex/bridge/.private/records/smallc-relogin-offer')

def notify(api, online, pending=None):
    pending = PENDING if pending is None else pending
    if online:
        pending.unlink(missing_ok=True)
    text = ('小c的 QQ 已恢复在线。' if online else
            '我这边检测到小c离线或连接异常。要我帮你重新登录吗？回我“好”就给你取登录二维码。')
    result=api('harness','send_private_msg',{'user_id':int(OWNER),'message':[{'type':'text','data':{'text':text}}],'auto_escape':True})
    if not isinstance(result,dict) or not result.get('message_id'):
        raise RuntimeError('health_notice_send_uncertain')
    if not online:
        temp = pending.with_suffix('.tmp')
        temp.write_text(str(time.time()))
        temp.chmod(0o600)
        temp.replace(pending)
    return result['message_id']
