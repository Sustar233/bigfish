"""Incremental daily pipeline: only uncached language work enters model context."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time

from daily import api, matching_answers, now, plain, question_id, read, render, select_topics, write, write_text
from preferences import apply_reading_preferences, clean_headline, reading_mode, rule_categories

EDITOR_VERSION = 'direct-voice-v1'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:24]


def language_key(kind, value, prefs):
    fields = [EDITOR_VERSION, kind, value, prefs['english_level'], prefs.get('answer_target_words', [120,220]), prefs.get('source_max_chars',5000)]
    if prefs.get('translation_style'):
        fields.append(prefs['translation_style'])
    return fingerprint(fields)


def load_cache(root):
    path = root / '.private' / 'editor-cache.json'
    return read(path) if path.exists() else {'topics': {}, 'answers': {}, 'labels': {}}


def topic_key(item, prefs):
    if reading_mode(item, prefs) == 'headline':
        return language_key('headline-v1', clean_headline(item['title']), prefs)
    if reading_mode(item, prefs) == 'deep':
        return language_key('deep-topic-v1', [item['title'], item['summary']], prefs)
    return language_key('topic', [item['title'], item['summary']], prefs)


def answer_key(item, answer, prefs):
    if reading_mode(item, prefs) == 'deep':
        return language_key('deep-answer-v1', [item['title'], answer['content'], prefs.get('preferred_answer_target_words', [220,340])], prefs)
    return language_key('answer', [item['title'], answer['content']], prefs)


def source_excerpt(text, limit):
    """Keep opening, middle and ending; explicitly disclose omitted source text."""
    if len(text) <= limit:
        return text, False
    first = limit // 2
    last = limit // 4
    middle = limit - first - last
    midstart = max(first, len(text) // 2 - middle // 2)
    return text[:first] + '\n[中间内容省略]\n' + text[midstart:midstart+middle] + '\n[中间内容省略]\n' + text[-last:], True


def make_work(source, prefs, cache):
    work = {'topics': [], 'answers': [], 'questions': {}}
    hits = {'topics': 0, 'answers': 0}
    for index,item in enumerate(source['items'],1):
        mode = reading_mode(item, prefs)
        if mode == 'headline':
            key = topic_key(item, prefs)
            if key in cache['topics']:
                hits['topics'] += 1
            else:
                work['topics'].append({'key':key, 'title':clean_headline(item['title']), 'reading_depth':'headline'})
            continue
        key = topic_key(item, prefs)
        if key in cache['topics']:
            hits['topics'] += 1
        else:
            work['topics'].append({'key': key, 'title': item['title'], 'summary': item['summary'], 'reading_depth': mode})
        for answer in item.get('answers', []):
            key = answer_key(item, answer, prefs)
            if key in cache['answers']:
                hits['answers'] += 1
            else:
                text, shortened = source_excerpt(answer['content'], prefs.get('source_max_chars', 5000))
                q = str(index)
                work['questions'][q] = item['title']
                work['answers'].append({'key': key, 'q': q, 'text': text, 'excerpted': shortened,
                                        'reading_depth': mode, 'target_words': prefs.get('preferred_answer_target_words', [220,340]) if mode == 'deep' else prefs.get('answer_target_words', [120,220])})
    return work, hits


def prepare(root, offline=False, resume=False):
    prefs = read(root / 'preferences.json')
    cache = load_cache(root)
    out = root / 'output'
    if offline:
        source = apply_reading_preferences(read(out / 'sources.json'), prefs)
    else:
        if resume:
            hot_data = read(out / 'hot.json')
            age = dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(hot_data['fetched_at'])
            if not dt.timedelta(minutes=-5) <= age <= dt.timedelta(hours=2):
                raise ValueError('Saved hot list is stale; run prepare without --resume')
            hot = hot_data['items']
        else:
            data = api('hot_list', {'Limit': 30})
            hot, seen = [], set()
            for rank, item in enumerate(data['Items'], 1):
                qid = question_id(item['Url'])
                if qid in seen:
                    continue
                seen.add(qid)
                hot.append({'id': qid, 'rank': rank, 'title': item['Title'], 'summary': plain(item.get('Summary','')), 'url': item['Url']})
            if not hot:
                raise ValueError('Empty live hot list')
            hot_data = {'fetched_at': now(), 'items': hot}
        required = sorted(set(prefs['exclude_topics'] + prefs['prefer_topics'] + prefs.get('headline_only_topics', [])) - set(prefs.get('topic_rules', {})))
        labels, missing = {}, []
        for item in hot:
            key = fingerprint([item['title'], item['summary'], required])
            known = rule_categories(item, prefs)
            if not required:
                labels[item['id']] = known
            elif key in cache['labels']:
                labels[item['id']] = cache['labels'][key] + known
            else:
                missing.append({'key': key, 'id': item['id'], 'title': item['title'], 'summary': item['summary']})
        write(out / 'hot.json', hot_data)
        if missing:
            write(out / 'classification-work.json', {'required_topics':required, 'items':missing})
            print(json.dumps({'status':'classification_needed','file':str(out/'classification-work.json'),'count':len(missing)},ensure_ascii=False))
            return
        source = apply_reading_preferences(dict(hot_data, items=select_topics(hot,prefs,labels)), prefs)
        network_cache_path = root / '.private' / 'answer-fetch-cache.json'
        network_cache = read(network_cache_path) if network_cache_path.exists() else {}
        for item in source['items']:
            if item['reading_depth'] == 'headline':
                continue
            cached = network_cache.get(item['id'], {})
            checked = cached.get('checked_at', 0)
            same_day = dt.datetime.fromtimestamp(checked, dt.timezone(dt.timedelta(hours=8))).date().isoformat() == source['fetched_at'][:10]
            if cached.get('title') == item['title'] and 0 <= time.time()-checked < 900 and same_day:
                item['answers'] = cached['answers'][:prefs['answers_per_topic']]
                item['answers_checked_at'] = cached['checked_at']
            else:
                try:
                    data = api('zhihu_search', {'Query':item['title'],'Count':10})
                    answers = matching_answers(data['Items'],item['id'],max(5, prefs['answers_per_topic']))
                    item['answers'] = answers[:prefs['answers_per_topic']]
                    item['answers_checked_at'] = time.time()
                    network_cache[item['id']] = dict(title=item['title'],answers=answers,checked_at=item['answers_checked_at'])
                    write(network_cache_path, network_cache)
                except ValueError as exc:
                    item['answers'] = []
                    item['answer_status'] = 'fetch_error'
                    item['answer_error'] = str(exc)
                time.sleep(.4)
        write(network_cache_path, network_cache)
        write(out / 'selected.json', source)
        write(out / 'sources.json', source)
    report_work(root, source, prefs, cache, offline)


def fetch_failures(source, prefs):
    return [{'id': x['id'], 'error': x.get('answer_error', x['answer_status'])}
            for x in source['items'] if reading_mode(x, prefs) != 'headline'
            and x.get('answer_status') not in (None, '', 'ok', 'no_matching_answer', 'no_matching_answers')]


def batch_work(work, max_chars=7500):
    """Keep tasks whole and emit only the question context the batch uses."""
    batch = {'topics': [], 'answers': [], 'questions': {}}
    for kind in ('topics', 'answers'):
        for task in work[kind]:
            trial = {k: list(batch[k]) for k in ('topics', 'answers')}
            trial['questions'] = dict(batch['questions'])
            trial[kind].append(task)
            if kind == 'answers':
                trial['questions'][task['q']] = work['questions'][task['q']]
            if len(json.dumps(trial, ensure_ascii=False, separators=(',', ':'))) > max_chars and (batch['topics'] or batch['answers']):
                return batch
            batch = trial
    return batch


def report_work(root, source, prefs, cache, offline=False):
    out = root/'output'
    failures = fetch_failures(source, prefs)
    work, hits = make_work(source, prefs, cache)
    if failures:
        work = {'topics': [], 'answers': [], 'questions': {}}
    write(out / 'language-work.json', work)
    batch = batch_work(work, prefs.get('language_batch_chars', 7500))
    write_text(out / 'language-batch.json', json.dumps(batch, ensure_ascii=False, separators=(',', ':')))
    chars = len(json.dumps(work,ensure_ascii=False,separators=(',',':')))
    report = {'status':'fetch_incomplete' if failures else 'language_needed' if work['topics'] or work['answers'] else 'ready_to_build',
              'file':str(out/'language-batch.json'),'topics':len(source['items']),
              'new_topics':len(work['topics']),'new_answers':len(work['answers']),
              'headline_only':sum(reading_mode(x,prefs)=='headline' for x in source['items']),
              'deep_topics':sum(reading_mode(x,prefs)=='deep' for x in source['items']),
              'cache_hits':hits,'model_input_chars':chars,'offline':offline,
              'batch_topics':len(batch['topics']), 'batch_answers':len(batch['answers']),
              'batch_input_chars':len(json.dumps(batch,ensure_ascii=False,separators=(',',':'))),
              'fetch_failures':failures,
              'without_answers':sum(not x.get('answers') and reading_mode(x,prefs) != 'headline' for x in source['items'])}
    write(out / 'work-report.json', report)
    print(json.dumps(report,ensure_ascii=False))


def import_labels(root, edits):
    work = read(root/'output/classification-work.json')
    cache = load_cache(root)
    supplied = read(edits)
    required = set(work['required_topics'])
    for item in work['items']:
        categories = supplied[item['key']]
        if not isinstance(categories,list) or not all(isinstance(c,str) for c in categories) or not set(categories)<=required:
            raise ValueError('Classification labels must be a subset of the requested topics')
        cache['labels'][item['key']] = categories
    write(root/'.private/editor-cache.json',cache)
    print('Classification cached. Run prepare --resume.')


def validate_edit(kind, value, mode, prefs):
    if not isinstance(value, dict):
        raise ValueError('Language edit must be an object')
    fields = ['title_en', 'title_zh'] if kind == 'topics' and mode == 'headline' else (
        ['title_en', 'summary_en', 'summary_zh'] if kind == 'topics' else ['headline_en'])
    if prefs.get('translation_style'):
        fields.append('title_zh' if kind == 'topics' else 'headline_zh')
    if any(not isinstance(value.get(k), str) or not value[k].strip() for k in fields):
        raise ValueError('Missing or empty bilingual language field')
    glossary = value.get('glossary', {})
    if not isinstance(glossary, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k,v in glossary.items()):
        raise ValueError('Glossary must contain text pairs')
    pairs = value.get('key_points', []) if kind == 'topics' else value.get('paragraphs')
    if not isinstance(pairs, list) or (kind == 'answers' and not pairs):
        raise ValueError('Answer paragraphs must be a nonempty bilingual list')
    for pair in pairs:
        if not isinstance(pair, dict) or any(not isinstance(pair.get(k), str) or not pair[k].strip() for k in ('en','zh')):
            raise ValueError('Each paragraph or key point requires both English and Chinese')
        if kind == 'answers' and (re.search(r'\b(the author|this author|this answer|the answer|the writer)\b',pair['en'],re.I) or re.search(r'作者(认为|指出|强调|表示)|这(条|篇)回答|答主认为',pair['zh'])):
            raise ValueError('Third-person reporting detected; preserve original voice')


def merge_edits(source, prefs, cache, changes):
    if not isinstance(changes, dict) or set(changes)-{'topics','answers'}:
        raise ValueError('Expected topics and answers edit maps')
    expected = {'topics': {}, 'answers': {}}
    for item in source['items']:
        mode = reading_mode(item, prefs)
        expected['topics'][topic_key(item,prefs)] = mode
        if mode != 'headline':
            for answer in item.get('answers', []):
                expected['answers'][answer_key(item,answer,prefs)] = mode
    for kind in ('topics','answers'):
        if not isinstance(changes.get(kind, {}), dict):
            raise ValueError('Language edits must be keyed objects')
        for key,value in changes.get(kind,{}).items():
            if key not in expected[kind]:
                raise ValueError('Unexpected edit key; prepare current sources first')
            validate_edit(kind, value, expected[kind][key], prefs)
    for kind in ('topics','answers'):
        cache[kind].update(changes.get(kind,{}))


def stage(root, edits):
    prefs = read(root/'preferences.json')
    source = apply_reading_preferences(read(root/'output/sources.json'), prefs)
    if fetch_failures(source, prefs):
        raise ValueError('Answer fetch incomplete; run prepare --resume first')
    cache = load_cache(root)
    merge_edits(source, prefs, cache, read(edits))
    write(root/'.private/editor-cache.json', cache)
    report_work(root, source, prefs, cache, offline=True)


def build(root, edits=None, preview=False):
    prefs = read(root/'preferences.json')
    source = apply_reading_preferences(read(root/'output/sources.json'), prefs)
    cache = load_cache(root)
    changes = read(edits) if edits else {'topics':{},'answers':{}}
    if fetch_failures(source, prefs):
        raise ValueError('Answer fetch incomplete; run prepare --resume first')
    merge_edits(source, prefs, cache, changes)
    glossary_path = Path(__file__).parent/'glossary.json'
    digest = {'fetched_at':source['fetched_at'],'items':[],'glossary':read(glossary_path) if glossary_path.exists() else {}}
    if not source['items']:
        raise ValueError('No topics remain after filtering; do not send an empty daily')
    for item in source['items']:
        mode = reading_mode(item, prefs)
        if mode == 'headline':
            edited = cache['topics'].get(topic_key(item,prefs))
            if not edited or not edited.get('title_en') or not edited.get('title_zh'):
                raise ValueError('Missing bilingual headline')
            validate_edit('topics', edited, mode, prefs)
            digest['items'].append({'id':item['id'], 'title_zh':edited['title_zh'], 'title_en':edited['title_en'],
                                   'summary_en':'', 'summary_zh':'', 'answers':[], 'reading_depth':'headline'})
            continue
        key = topic_key(item,prefs)
        if key not in cache['topics']:
            raise ValueError('Missing topic language work')
        edited = cache['topics'][key]
        validate_edit('topics', edited, mode, prefs)
        if prefs.get('translation_style') and not edited.get('title_zh'):
            raise ValueError('A literal Chinese translation of the English title is required')
        result = {'id':item['id'],'title_zh':edited.get('title_zh',item['title']),'title_en':edited['title_en'],
                  'summary_en':edited['summary_en'],'summary_zh':edited['summary_zh'],'answers':[],
                  'reading_depth':mode,'key_points':edited.get('key_points', [])}
        digest['glossary'].update(edited.get('glossary',{}))
        for answer in item.get('answers',[]):
            key = answer_key(item,answer,prefs)
            if key not in cache['answers']:
                raise ValueError('Missing answer language work')
            edited = cache['answers'][key]
            validate_edit('answers', edited, mode, prefs)
            if prefs.get('translation_style') and not edited.get('headline_zh'):
                raise ValueError('A literal Chinese translation of the answer heading is required')
            paras = edited['paragraphs']
            result['answers'].append({'id':answer['id'],'headline_en':edited['headline_en'],
                                      'headline_zh':edited.get('headline_zh',''),
                                      'paragraphs':paras,'summary_en':'\n\n'.join(p['en'] for p in paras),
                                      'summary_zh':'\n\n'.join(p['zh'] for p in paras)})
            digest['glossary'].update(edited.get('glossary',{}))
        digest['items'].append(result)
    full,email = render(digest,source,preview=preview)
    write(root/'output/digest.json',digest)
    write_text(root/'output/zhihu-daily.html',full)
    write_text(root/'output/email.html',email)
    write(root/'.private/editor-cache.json',cache)
    report = {'status':'built','topics':len(digest['items']),'answers':sum(len(x['answers']) for x in digest['items']),
              'reader':str(root/'output/zhihu-daily.html'),'preview':preview,
              'digest_hash':fingerprint(digest),'source_hash':fingerprint(source),'preferences_hash':fingerprint(prefs)}
    write(root/'output/build-report.json',report)
    print(json.dumps(report,ensure_ascii=False))


def mail(root):
    prefs = read(root/'preferences.json')
    if prefs['delivery'] != 'html_attachment' or not prefs.get('recipient'):
        raise ValueError('Mail delivery is not configured')
    report = read(root/'output/build-report.json')
    if report['preview']:
        raise ValueError('Preview edition cannot be sent as a fresh daily')
    source = apply_reading_preferences(read(root/'output/sources.json'), prefs)
    from daily import validate_digest
    digest = read(root/'output/digest.json')
    if fetch_failures(source, prefs):
        raise ValueError('Answer fetch incomplete; run prepare --resume first')
    validate_digest(digest,source)
    for name,value in (('digest',digest),('source',source),('preferences',prefs)):
        if report.get(name+'_hash') != fingerprint(value):
            raise ValueError('Build inputs changed; run build before mail')
    delivery_key = fingerprint([source['fetched_at'][:10],prefs['recipient'],{k:v for k,v in digest.items() if k!='fetched_at'}])
    if delivery_key in delivery_history(root):
        raise ValueError('This edition was already sent to this recipient')
    # Re-render validated inputs; an old or manually replaced HTML cannot leak into mail.
    full,email = render(digest,source)
    payload={'to':prefs['recipient'],'subject':'知乎日报｜'+source['fetched_at'][:10]+'｜英文精读版',
             'payload':{'mime_type':'multipart/mixed','parts':[
                 {'mime_type':'text/html','charset':'UTF-8','body':{'content':email}},
                 {'mime_type':'text/html','charset':'UTF-8','filename':'zhihu-daily-'+source['fetched_at'][:10]+'.html','content_disposition':'attachment','body':{'content':full}}]},
             'response_fields':['id','thread_id','label_ids']}
    pending = {'delivery_key':delivery_key,'recipient':prefs['recipient'],
               'source_fetched_at':source['fetched_at'],'prepared_at':now()}
    try:
        with (root/'output/pending-delivery.json').open('x',encoding='utf-8') as handle:
            json.dump(pending,handle,ensure_ascii=False)
    except FileExistsError:
        raise ValueError('Pending delivery exists; check sent mail, then record or release it before retrying') from None
    print(json.dumps(payload,ensure_ascii=True,separators=(',',':')))


def delivery_history(root):
    path = root/'.private/delivery-history.json'
    history = read(path) if path.exists() else {}
    lastpath = root/'output/last-delivery.json'
    if lastpath.exists():
        last = read(lastpath)
        if last.get('delivery_key') and last.get('message_id'):
            history.setdefault(last['delivery_key'], last)
    return history


def record_delivery(root, message_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',message_id):
        raise ValueError('Unexpected message ID')
    history = delivery_history(root)
    path = root/'output/pending-delivery.json'
    if not path.exists():
        if any(x.get('message_id') == message_id for x in history.values()):
            print('Delivery already recorded.')
            return
        raise ValueError('No pending delivery to record')
    pending = read(path)
    previous = history.get(pending['delivery_key'])
    if previous and previous['message_id'] != message_id:
        raise ValueError('Message ID conflicts with recorded delivery')
    record = previous or dict(pending,message_id=message_id,sent_at=now())
    history[pending['delivery_key']] = record
    # Persist the durable history before clearing the reservation. A failed write
    # leaves the reservation in place, preventing an uncertain automatic resend.
    write(root/'.private/delivery-history.json', history)
    write(root/'output/last-delivery.json', record)
    path.unlink()
    print('Delivery recorded.')


def release_delivery(root, delivery_key, reason):
    path = root/'output/pending-delivery.json'
    pending = read(path)
    if pending['delivery_key'] != delivery_key or delivery_key in delivery_history(root):
        raise ValueError('Reservation mismatch or already sent; use record for a confirmed delivery')
    if not reason.strip():
        raise ValueError('Explain how non-delivery was confirmed')
    write(root/'output/released-delivery.json',dict(pending,reason=reason,released_at=now()))
    path.unlink()
    print('Unsent reservation released.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',type=Path,default=Path('F:/codexCoding/dailyZhihu'))
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('--offline',action='store_true');p.add_argument('--resume',action='store_true')
    p=sub.add_parser('classify');p.add_argument('--edits',type=Path,required=True)
    p=sub.add_parser('stage');p.add_argument('--edits',type=Path,required=True)
    p=sub.add_parser('build');p.add_argument('--edits',type=Path);p.add_argument('--preview',action='store_true')
    sub.add_parser('mail')
    p=sub.add_parser('record');p.add_argument('--message-id',required=True)
    p=sub.add_parser('release');p.add_argument('--delivery-key',required=True);p.add_argument('--confirmed-unsent',required=True)
    args=parser.parse_args()
    if args.action=='prepare':prepare(args.workspace,args.offline,args.resume)
    elif args.action=='classify':import_labels(args.workspace,args.edits)
    elif args.action=='stage':stage(args.workspace,args.edits)
    elif args.action=='build':build(args.workspace,args.edits,args.preview)
    elif args.action=='mail':mail(args.workspace)
    elif args.action=='record':record_delivery(args.workspace,args.message_id)
    elif args.action=='release':release_delivery(args.workspace,args.delivery_key,args.confirmed_unsent)


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(f'Error: {exc}',file=sys.stderr);sys.exit(1)
