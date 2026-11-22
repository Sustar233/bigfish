"""Flush prepared news only: no fetching, editing or extra model calls."""


def flush_recovery(state, config, flush):
    outcomes = []
    for kind in ('digest', None):
        result = flush(state, config, kind=kind)
        outcomes.append(result)
        if result in ('quiet_hours', 'qq_offline_pending', 'uncertain_no_retry'):
            break
    if any(value.startswith('sent_') for value in outcomes):
        status = 'sent'
    else:
        status = outcomes[-1]
    return {'status': status, 'outcomes': outcomes}
