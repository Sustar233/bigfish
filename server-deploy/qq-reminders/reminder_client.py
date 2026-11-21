from datetime import datetime, timedelta, timezone
import json
import re
import socket

TZ = timezone(timedelta(hours=8))


def call(request):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(12)
        connection.connect('/run/qq-reminders/control.sock')
        connection.sendall((json.dumps(request,ensure_ascii=False)+'\n').encode())
        result=json.loads(connection.makefile('rb').readline(65536))
    if not result['ok']:
        raise ValueError(result['error'])
    return result['result']


def number(s):
    if s.isdigit():return int(s)
    digits=dict(zip('零一二三四五六七八九',range(10)));digits['两']=2
    if s=='半':return .5
    if '十' in s:
        a,b=s.split('十');return digits.get(a,1)*10+digits.get(b,0)
    if s in digits:return digits[s]
    raise ValueError('时间数字不明确')


NUM=r'[0-9零一二两三四五六七八九十]+'


def parse(text, now=None):
    now=now or datetime.now(TZ)
    s=text.strip().replace('明早','明天早上').replace('明晚','明天晚上').replace('半个小时','30分钟').replace('半小时','30分钟').replace('一个小时','1小时')
    if s in ('/提醒列表','/查看提醒','有哪些提醒','我有哪些提醒','我有哪些定时提醒') or re.fullmatch(r'(?:帮我)?(?:查看|列出|看看)(?:我(?:的)?)?(?:所有|全部)?提醒(?:列表)?',s):
        return {'action':'list'}
    match=re.fullmatch(r'/?取消提醒\s+([a-f0-9]{12})',s)
    if match:return {'action':'cancel','reminder_id':match[1]}
    if re.fullmatch(r'取消(?:刚才|上一个|最新|这个|那个)(?:的)?提醒',s):
        return {'action':'cancel','reminder_id':'latest'}
    marker=re.search(r'(提醒(?:一下)?我|给我发(?:一条|一句|个|消息)?|发消息给我)\s*[:：]?\s*(.+)$',s)
    if not marker:return None
    before=s[:marker.start()];message=marker[2].strip()
    if any(w in before for w in ('比如','例如','举个例子','之前说','不要','不用','不需要')):return None
    # Also accept “提醒我明天8点喝水” by moving only the detected time prefix.
    if not re.search(r'后|点|\d:\d|每天|每日|工作日|每周|明天|后天|今天',before) and re.match(r'(?:每天|每日|每周|工作日|明天|后天|今天|晚上|早上|下午|\d)',message):
        s=message;before=s;message=''
    delay=re.search(r'('+NUM+r'|半)\s*(秒钟|秒|分钟|分|小时|天)(?:以?后|之后)',before)
    result={'action':'create','repeat':'none'}
    time_end=0
    interval=re.search(r'每(?:隔)?('+NUM+r'|半)\s*(分钟|小时|天)',before)
    if interval:
        result.update(repeat='interval',interval_minutes=number(interval[1])*{'分钟':1,'小时':60,'天':1440}[interval[2]])
        time_end=interval.end()
    elif delay:
        seconds=number(delay[1])*{'秒钟':1,'秒':1,'分钟':60,'分':60,'小时':3600,'天':86400}[delay[2]]
        result['fire_at']=(now+timedelta(seconds=seconds)).isoformat();time_end=delay.end()
    else:
        clock=re.search(r'('+NUM+r')\s*(?:点|:|：)(?:('+NUM+r')\s*分?|(半))?',before)
        if not clock:return None
        hour=number(clock[1]);minute=30 if clock[3] else number(clock[2]) if clock[2] else 0
        if any(w in before[:clock.start()] for w in ('下午','晚上','傍晚','中午')) and hour<12:hour+=12
        if '凌晨' in before and hour==12:hour=0
        if hour>23 or minute>59:raise ValueError('时间超出范围')
        at=f'{int(hour):02d}:{int(minute):02d}';time_end=clock.end()
        if '工作日' in before:result.update(repeat='weekdays',at=at)
        elif '每天' in before or '每日' in before:result.update(repeat='daily',at=at)
        elif (week:=re.search(r'每周([一二三四五六日天])',before)):
            result.update(repeat='weekly',at=at,weekdays=str('一二三四五六日'.index(week[1].replace('天','日'))))
        else:
            date=now
            if '后天' in before:date+=timedelta(days=2)
            elif '明天' in before:date+=timedelta(days=1)
            elif (explicit:=re.search(r'(\d{4})[-年](\d{1,2})[-月](\d{1,2})[日号]?',before)):
                date=date.replace(year=int(explicit[1]),month=int(explicit[2]),day=int(explicit[3]))
            fire=date.replace(hour=int(hour),minute=int(minute),second=0,microsecond=0)
            if fire<=now and not any(x in before for x in ('今天','今晚','明天','后天')) and not re.search(r'\d{4}[-年]',before):fire+=timedelta(days=1)
            result['fire_at']=fire.isoformat()
    if '每' in before and result['repeat']=='none':raise ValueError('重复时间没读清楚，请明确说每天、工作日、每周几或每隔几分钟')
    if not message:message=s[time_end:].strip(' ，,：:')
    if not message:raise ValueError('请补充提醒内容')
    result['message']=message
    return result


def format_result(result):
    if isinstance(result,list):
        if not result:return '目前没有待发送的提醒。'
        return '\n'.join(f"{x['id']}｜{x['next_fire_beijing'][:16].replace('T',' ')}｜{x['message']}｜{x['state']}" for x in result)
    if result['state']=='cancelled':return f"已取消提醒 {result['id']}。若消息已在发送途中，可能仍会收到。"
    repeat={'none':'一次','daily':'每天','weekdays':'工作日','weekly':'每周','interval':'重复'}[result['spec']['repeat']]
    return f"已设置{repeat}提醒：{result['message']}\n下次：{result['next_fire_beijing'][:16].replace('T',' ')}（北京时间）\n编号：{result['id']}"


def private_command(text,key,owner):
    try:
        identity=dict(owner=str(owner),channel='private',origin='smallc-private-'+str(owner),bot='smallc')
        edit=re.fullmatch(r'(?:把|将)?(?:刚才|最新|这个|那个)(?:的)?提醒(?:时间)?(?:改到|改成|改为|推迟到)(.+)',text.strip())
        explicit=re.fullmatch(r'/修改提醒\s+([a-f0-9]{12})\s+(.+)',text.strip())
        if edit or explicit:
            existing=call(dict(identity,action='list'))
            selected=next((r for r in existing if r['id']==explicit[1]),None) if explicit else next(iter(existing),None)
            if not selected:raise ValueError('没找到要修改的提醒')
            time_text=explicit[2] if explicit else edit[1]
            args=parse(time_text+'提醒我'+selected['message'])
            if args is None:raise ValueError('修改后的时间不明确，请补充具体时间')
            args.update(action='update',reminder_id=selected['id'])
        else:
            args=parse(text)
        if args is None:return None
        args.update(identity,request_key=str(key))
        return format_result(call(args))
    except Exception as error:
        return '提醒操作未完成：'+str(error)
