"""Route only smallc health transitions to the owner's whale QQ account."""
OWNER='1000000001'


def notify(api, online):
    text = ('小c回来啦，已经核对是原来的账号，可以继续找它聊天了。' if online else
            '小c这边暂时接不到消息，可能掉线或接口异常。需要重新登录的话直接跟我说，我帮你取小c的新二维码，不用记固定口令。')
    result=api('harness','send_private_msg',{'user_id':int(OWNER),'message':[{'type':'text','data':{'text':text}}],'auto_escape':True})
    if not isinstance(result,dict) or not result.get('message_id'):
        raise RuntimeError('health_notice_send_uncertain')
    return result['message_id']
