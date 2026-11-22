"""Resolve private drawing references inside the requesting conversation's job store."""
import re
from pathlib import Path
from image_batch import number

TTL = 24 * 3600


def previous(db, bot, prompt, quote, now):
    if quote is not None:
        row = db.execute("""SELECT id FROM jobs WHERE bot=? AND message_id=? AND status='sent'
                            AND updated>=? ORDER BY updated DESC LIMIT 1""", (bot, str(quote), now-TTL)).fetchone()
        if row:
            return row[0]
        raise ValueError('missing_image')
    row = db.execute("""SELECT id,event_key FROM jobs WHERE bot=? AND status='sent'
                        AND updated>=? ORDER BY updated DESC,created DESC LIMIT 1""", (bot, now-TTL)).fetchone()
    if row:
        batch = row[1].split('/')[1] if row[1].startswith('\x00batch/') else row[0]
        rows = db.execute("""SELECT id FROM jobs WHERE bot=? AND (id=? OR instr(event_key,?)=1)
                             AND status='sent' AND updated>=? ORDER BY updated,created""",
                          (bot, batch, '\x00batch/'+batch+'/', now-TTL)).fetchall()
        which = re.search(r'第\s*([0-9一二两三四五六七八九十]+)\s*张', prompt)
        index = number(which[1])-1 if which else len(rows)-1
        if 0 <= index < len(rows):
            return rows[index][0]
    raise ValueError('missing_image')


def cached_input(service, job):
    with service.db() as db:
        row = db.execute("SELECT image_path FROM jobs WHERE id=? AND bot=? AND status='sent'",
                         (job['source_message_id'], job['bot'])).fetchone()
    if not row or not row[0]:
        raise RuntimeError('attachment')
    path = Path(row[0]).resolve()
    if path.parent != (service.private/'outputs'/job['source_message_id']).resolve() or not path.is_file():
        raise RuntimeError('attachment')
    return path


def portrait(role, prompt, card_root):
    if not re.search(r'(?:画|绘|来张|来一张|生成|照片|自拍).{0,18}(?:你自己|你在|你的(?:照片|样子|头像|自拍)|你一张|张你)|你的自拍', prompt):
        return prompt, None
    card = card_root/(str(role.port)+'.txt')
    description = card.read_text(encoding='utf-8').strip()[:1000] if card.is_file() else ''
    reference = card.with_suffix('.png')
    if description:
        prompt += '\n角色的固定外观：'+description
    return prompt, reference if reference.is_file() else None
