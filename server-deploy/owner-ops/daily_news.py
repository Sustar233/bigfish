"""Apply private QQ topic preferences through the active news collector's store."""
import fcntl
from pathlib import Path
import sys

ROOT = Path('/home/ubuntu/server-maintenance/news')
sys.path.insert(0, str(ROOT))
import news_preferences as prefs


def answer(action, topic, root=ROOT):
    if action not in ('show', 'more', 'less', 'normal') or (action != 'show' and topic not in prefs.CATEGORIES):
        raise ValueError('unknown news preference')
    private = root / '.private'
    # Newer collector versions expose a coordinated writer; older ones
    # serialize the whole collection cycle on run.lock.
    if hasattr(prefs, 'update'):
        request = {'action': 'show'} if action == 'show' else (
            {'action': 'set_weight', 'topic': topic, 'weight': 1} if action == 'normal'
            else {'action': 'adjust_weight', 'topic': topic, 'direction': action})
        data = prefs.update(request, root=root)
    else:
        path = private / 'interest_preferences.json'
        with (private / 'run.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            data = prefs.load(path)
            if action != 'show':
                before = data['topic_weights'][topic]
                weight = 1 if action == 'normal' else max(.25,min(5,before*(1.25 if action=='more' else .8)))
                data['topic_weights'][topic] = round(weight, 4)
                prefs.save(path, data)
    weights = data['topic_weights']
    if action == 'show':
        return '你现在的新闻偏好是（1 为平常频率）：' + '、'.join(f'{k} {v:g}' for k,v in weights.items()) + '。'
    return f'调好了，{topic}的新闻权重现在是 {weights[topic]:g}（平常是 1）。'


if __name__ == '__main__':
    try:
        print(answer(*sys.argv[1:]))
    except BlockingIOError:
        print('这会儿新闻正在采集，偏好还没改。等一会儿再跟我说一次就行。')
