"""Deterministic time/session policy and public-query routing; no network access."""
from datetime import datetime, timezone, timedelta
import ipaddress
import re
import time
from urllib.parse import urlsplit

TZ = timezone(timedelta(hours=8), 'Asia/Shanghai')
SOFT_IDLE = 2 * 3600
NEW_SESSION_IDLE = 6 * 3600


def timestamp(value):
    if value is None:
        return '原始时间未知'
    return datetime.fromtimestamp(value, TZ).isoformat(timespec='seconds')


def prepare_history(messages, now=None):
    """Keep the latest contiguous session; never delete the durable archive."""
    now = time.time() if now is None else now
    known = [dict(m) for m in messages if isinstance(m.get('occurred'), (int, float))]
    last_user = next((m['occurred'] for m in reversed(known) if m['role'] == 'user'), None)
    gap = max(0, now - last_user) if last_user is not None else None
    state = 'new' if gap is None or gap >= NEW_SESSION_IDLE else 'soft' if gap >= SOFT_IDLE else 'continuing'
    selected = []
    if state != 'new':
        # A long gap anywhere in the rolling window is also a session boundary.
        for m in reversed(known):
            if selected and selected[-1]['occurred'] - m['occurred'] >= NEW_SESSION_IDLE:
                break
            selected.append(m)
        selected.reverse()
        if state == 'soft':
            selected = selected[-4:]
        selected = selected[-40:]
        while selected and sum(len(x['content']) for x in selected) > 16000:
            selected.pop(0)
    metadata = {'current_time': timestamp(now), 'timezone': 'Asia/Shanghai',
                'last_user_at': timestamp(last_user),
                'gap_seconds': int(gap) if gap is not None else None,
                'session_state': state}
    history = [{'role': m['role'], 'content': m['content'],
                'occurred': m['occurred'], 'sent_at': timestamp(m['occurred'])}
               for m in selected]
    return history, metadata


def wants_archive(query):
    # Archive search is opt-in by conversational intent, not triggered by greetings.
    return bool(re.search(r'昨天|前天|上[周月次回]|之前|以前|还记得|记不记得|接着|继续.{0,8}(聊|说|那个)|那件事|上文|前面说', query))


def public_url(url):
    if not isinstance(url, str) or len(url) > 2000 or any(c.isspace() for c in url):
        return False
    try:
        p = urlsplit(url)
        host = (p.hostname or '').lower().rstrip('.')
        if p.scheme not in ('http', 'https') or not host or p.username or p.password:
            return False
        if p.port not in (None, 80, 443):
            return False
        if host in ('localhost', 'metadata.google.internal') or '.' not in host:
            return False
        if host.endswith(('.localhost', '.local', '.internal', '.lan', '.home')):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            # Numeric legacy forms (127.1 / 2130706433 / octal / hex) are not hostnames.
            if re.fullmatch(r'[0-9.]+|0x[0-9a-f]+', host):
                return False
            return True
    except (ValueError, TypeError):
        return False


def search_mode(query):
    """Use only the authenticated human's current message to choose capabilities."""
    urls = re.findall(r'https?://[^\s<>"，。]+', query)
    if any(not public_url(u) for u in urls):
        return 'blocked'
    if re.search(r'(?:密码|口令|授权码|api.?key|secret|token)\s*[:：=]|sk-[\w-]{16,}|Bearer\s+|BEGIN .*PRIVATE KEY', query, re.I):
        return 'blocked'
    explicit = bool(re.search(r'联网|搜索|搜一下|帮我搜|查一下|查一查|帮我查|查查|查询|查下|search\b|look up\b', query, re.I))
    fresh_subject = bool(re.search(r'天气|气温|新闻|热搜|比分|赛程|股价|汇率|版本|发布|票价|价格|路况|营业', query))
    fresh = bool(re.search(r'今天|今日|现在|目前|当前|实时|最新|最近|本周|明天|这周', query))
    if urls or explicit or (fresh and fresh_subject) or re.search(r'(天气|气温|汇率|股价)(怎么样|多少|如何|预报|呢|[？?])', query):
        return 'live' if fresh or fresh_subject else 'cached'
    return 'disabled'
