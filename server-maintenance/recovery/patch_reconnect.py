"""Minimal patches to live routines; retain their locks, queues and deduplication."""
import ast


def once(source, anchor, replacement):
    source=source.replace('\r\n','\n')
    if source.count(anchor)!=1:
        raise ValueError('unexpected_reconnect_anchor: '+anchor[:70])
    return source.replace(anchor,replacement,1)


def weather(source):
    source=once(source,"    parser.add_argument('--status', action='store_true')\n",
        "    parser.add_argument('--status', action='store_true')\n    parser.add_argument('--catch-up', action='store_true')\n")
    anchor='            expired = state.expire_pending(now)\n'
    source=once(source,anchor,
        "            if args.catch_up:\n"
        "                from weather_catchup import catch_up\n"
        "                result = catch_up(state, now, collect, WeatherQQ, deliver)\n"
        "                print(json.dumps(result, ensure_ascii=False))\n"
        "                return 0\n"+anchor)
    ast.parse(source);return source


def news(source):
    source=once(source,'def flush(state, config, qq=None, now=None):','def flush(state, config, qq=None, now=None, kind=None):')
    anchor='WHERE status=\'pending\' AND not_before<=? ORDER BY CASE kind'
    source=once(source,anchor,"WHERE status='pending' AND not_before<=? AND (? IS NULL OR kind=?) ORDER BY CASE kind")
    source=once(source,'END,created LIMIT 12", (now,)).fetchall()', 'END,created LIMIT 12", (now,kind,kind)).fetchall()')
    source=once(source,"    parser.add_argument('--status', action='store_true')\n",
        "    parser.add_argument('--status', action='store_true')\n    parser.add_argument('--flush-only', action='store_true')\n")
    anchor="            else:\n                mode = args.mode\n"
    source=once(source,anchor,
        "            elif args.flush_only:\n"
        "                from news_recovery import flush_recovery\n"
        "                print(json.dumps(flush_recovery(state, config, flush)))\n"+anchor)
    ast.parse(source);return source


def health(source):
    source=source.replace('\r\n','\n')
    anchor="        if label == 'codex':\n            from standby import sync_health\n            sync_health(online, failures)\n"
    hook=(
        "            try:\n"
        "                from reconnect_push import heartbeat as recovery_heartbeat\n"
        "                recovery_heartbeat(online)\n"
        "            except Exception as exc:\n"
        "                print(json.dumps({'event':'reconnect_catchup_failed','error_type':type(exc).__name__}))\n")
    if anchor in source:
        source=once(source,anchor,anchor+hook)
    else:
        anchor="        failures = 0 if online else old.get('failures', 0)+1\n"
        source=once(source,anchor,anchor+"        if label == 'codex':\n"+hook)
    ast.parse(source);return source


def login(source):
    anchor="    result['checked_at'] = datetime.now().astimezone().isoformat()\n"
    source=once(source,anchor,
        "    if result.get('status') == 'online' and result.get('expected_account') is True:\n"
        "        try:\n"
        "            import sys\n"
        "            sys.path.insert(0, '/home/ubuntu/qq-codex/bridge')\n"
        "            from reconnect_push import heartbeat\n"
        "            result['catchup_scheduled'] = heartbeat(True)\n"
        "        except Exception as exc:\n"
        "            result['catchup_error_type'] = type(exc).__name__\n"+anchor)
    ast.parse(source);return source
