"""Plan independent output files for an explicitly multi-image request."""
import hashlib
import re
import unicodedata


NUMBER = r'[0-9]+|[一二两三四五六七八九十百]+|多|几'
DIGITS = dict(zip('一二三四五六七八九', range(1, 10)), 两=2)


def number(value):
    if value.isdecimal():
        return int(value[:4])
    if value in ('多', '几'):
        return 3
    if value in DIGITS:
        return DIGITS[value]
    if '百' not in value and value.count('十') == 1:
        left, right = value.split('十')
        return 10 * DIGITS.get(left, 1) + DIGITS.get(right, 0)
    return 100


def prompts_for(prompt):
    text = unicodedata.normalize('NFKC', prompt).strip()
    # An explicit single composite is an output format in its own right.
    if re.search(r'(?:拼成|合成|排成|放在|放到|放进|拼在|合并成)\s*(?:同)?一[张幅]|(?:生成|画|制作)\s*一张.{0,8}(?:拼贴|宫格|拼图)', text):
        return [prompt]
    quantity = rf'({NUMBER})\s*[张幅]'
    match = re.search(r'(?<!不)(?:生成|画出|画|绘制|制作|输出|给我|来|需要|想要|要|出图|共|总计)\s*(?:出|共|一共|独立的)?\s*' + quantity, text)
    if not match:
        match = re.search(r'[,，；;、：:\s]\s*' + quantity + r'(?:独立|不同|单独|分别|图|插画|照片|海报|壁纸|[，,。！!]|$)', text)
    if not match:
        match = re.search(r'(?:再给我|给我|再来|做|出)\s*('+NUMBER+r')\s*(?:个|种)版本', text)
    if not match:
        match = re.match(quantity, text)
    if not match:
        match = re.search(r'(?:生成|create|generate|draw)\s*(\d+)\s*(?:separate\s+)?(?:images|pictures|illustrations)\b', text, re.I)
    if not match:
        return [prompt]
    count = number(match[1])
    if count == 1:
        return [prompt]
    if not 2 <= count <= 32:
        raise ValueError('invalid_prompt')
    return [f'本次只生成整组 {count} 张中的第 {i} 张独立成图。若有顺序或分项，'
            f'只画对应第 {i} 项；共用主题则换一个构图。铺满单幅画面，禁止拼贴、分屏、宫格或展示整组。'
            f'\n原始整组要求：{prompt}' for i in range(1, count + 1)]


def enqueue(db, jobid, bot, key, prompt, now, kind, source):
    prompts = prompts_for(prompt)
    for index, description in enumerate(prompts):
        event = key if index == 0 else f'\x00batch/{jobid}/{index}'
        ident = jobid if index == 0 else hashlib.sha256((bot + '/' + event).encode()).hexdigest()[:16]
        db.execute('''INSERT INTO jobs
            (id,bot,event_key,prompt,status,created,updated,kind,source_message_id)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (ident,bot,event,description,'queued',now + index / 100000,now,kind,source))
