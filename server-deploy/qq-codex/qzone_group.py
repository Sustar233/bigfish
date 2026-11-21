"""Explicit group Qzone commands, behind Room's owner and event-dedup gates."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from qzone_commands import parse, qzone_command

NAMES = {'小c': 'codex', 'codex': 'codex', '大肥鱼': 'harness', 'deepseek': 'harness'}


def plan(text, mentions, accounts):
    text = re.sub(r'\s+', '', text.strip()).rstrip('。！!').lower()
    explicit = []
    while True:
        match = re.match(r'^(小c|codex|大肥鱼|deepseek)(?:和|跟|与|、|，|,|：|:)?', text)
        if match is None:
            break
        explicit.append(NAMES[match[1]])
        text = text[match.end():]
    collective = False
    for word in ('你们俩', '你们两个', '你们', '大家'):
        if text.startswith(word):
            collective = True
            text = text[len(word):]
            break
    if text.startswith(('一起', '都')):
        collective = True
        text = re.sub(r'^(?:一起|都)', '', text, count=1)
    action = parse(text)
    if action not in ('like', 'status'):
        return None
    mentioned = [label for label in accounts if str(accounts[label]) in {str(v) for v in mentions}]
    labels = list(accounts) if collective else list(dict.fromkeys(explicit or mentioned or list(accounts)))
    return action, labels


def handle_group_qzone(room, key, text, mentions, owner, group, accounts, private):
    chosen = plan(text, mentions, accounts)
    if chosen is None:
        return False
    action, labels = chosen
    if room.control.get('paused') == '1':
        room.notice('群聊暂停中，先说“继续群聊”，或者私聊我发 /空间点赞。')
        return True
    if not room.members_safe():
        return True
    pending = []
    for label in labels:
        call = room.control.reserve(key, label)
        if call is not None:
            pending.append((label, call))
    if not pending:
        room.notice('这会儿群聊请求有点密，稍后再来；也可以私聊发 /空间点赞。')
        return True

    def execute(label):
        endpoint = room.endpoints.get(label)
        if endpoint is None:
            return '我这边QQ暂时没连上，没有发起点赞。'
        config = endpoint.config
        if str(config.get('owner_qq')) != str(owner) or str(config.get('bot_qq')) != str(accounts[label]):
            return '当前QQ身份不匹配，没有发起点赞。'
        return qzone_command('/空间点赞' if action == 'like' else '/空间状态',
                             endpoint.request, config, private[label])

    with ThreadPoolExecutor(max_workers=len(pending)) as pool:
        futures = {pool.submit(execute, label): (label, call) for label, call in pending}
        for future in as_completed(futures):
            label, call = futures[future]
            event_key = key + '/qzone/' + label
            try:
                reply = future.result()
            except Exception:
                reply = '我这边空间接口暂时没接上，没有确认点赞成功。'
            try:
                room.data.record(event_key, 'assistant', reply, status='generated', source='qq-group-qzone',
                    payload={'group_id': group, 'speaker': '小c' if label == 'codex' else '大肥鱼',
                             'sender': accounts[label]})
                room.send(label, reply)
                room.data.mark(event_key, 'sent')
                room.control.mark(call, 'sent')
            except Exception:
                room.data.mark(event_key, 'failed_or_uncertain')
                room.control.mark(call, 'failed_or_uncertain')
    return True
