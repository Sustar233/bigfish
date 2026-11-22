"""Deliver today's missed weather after reconnect, including deadline-expired rows."""
from datetime import datetime


def catch_up(state, now, collect, qq_factory, deliver):
    day = now.date().isoformat()
    if now.hour < 6:
        return {'status': 'not_due', 'day': day}
    if state.get(day) in ('sent', 'sending', 'uncertain'):
        return {'status': 'already_handled', 'day': day}
    row = state.db.execute('SELECT updated,body FROM forecasts WHERE day=?', (day,)).fetchone()
    if row and datetime.fromisoformat(row[0]).date() == now.date() and row[1]:
        updated, text = row
        prefix = f'小c上线啦，补上今天漏送的天气。这是{datetime.fromisoformat(updated):%H:%M}生成的早间预报。'
        if now.hour >= 19:
            prefix += '今天的通勤时段已过，以下作为早报补发，不是实时天气。'
        elif now.hour >= 10:
            prefix += '上午通勤时段已过，晚间部分仍可参考。'
        text = prefix + '\n\n' + text
    else:
        try:
            text = collect(now)
        except Exception as exc:
            state.put(day, 'queued', now, error=type(exc).__name__)
            return {'status': 'source_unavailable', 'day': day}
        with state.db:
            state.db.execute('INSERT OR REPLACE INTO forecasts VALUES(?,?,?)', (day, now.isoformat(), text))
        text = '小c上线啦，补上今天漏送的天气。\n\n' + text
    try:
        qq = qq_factory()
    except Exception as exc:
        state.put(day, 'queued', now, error=type(exc).__name__)
        return {'status': 'qq_configuration_error', 'day': day}
    return {'status': deliver(state, now, text, qq), 'day': day}
