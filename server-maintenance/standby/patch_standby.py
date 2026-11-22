"""Guard owner reception before every task/model route; preserve live source."""
import ast


def once(source, old, new):
    source = source.replace('\r\n', '\n')
    if source.count(old) != 1:
        raise ValueError('unexpected_standby_anchor: '+old[:70])
    return source.replace(old, new, 1)


def smallc(source):
    source=once(source,"                voice_image_reply = None\n", "                from standby import reply_if_active\n                standby_reply = reply_if_active(text, 'smallc')\n                voice_image_reply = None\n")
    start=source.index('                voice_image_reply = None\n')
    end=source.index('                if reply is not None:\n',start)
    block=source[start:end]
    source=source[:start]+("                if standby_reply is not None:\n"
        "                    reply, export_path = standby_reply, None\n"
        "                    media_command = None\n"
        "                    choices['quiet'] = True\n"
        "                else:\n"+''.join('    '+line if line.strip() else line for line in block.splitlines(True)))+source[end:]
    start=source.index("                        reply = {'quota':")
    end=source.index('                        append = False',start)
    source=source[:start]+("                        from standby import State, reception\n"
        "                        State().failed(code)\n"
        "                        reply = reception(text, 'smallc', 'model')\n"
        "                        choices['quiet'] = True\n")+source[end:]
    ast.parse(source);return source


def maintenance(source):
    source=once(source,"        online = onebot_state == 'ready'\n", "        online = onebot_state == 'ready'\n")
    source=once(source,"        failures = 0 if online else old.get('failures', 0)+1\n",
        "        failures = 0 if online else old.get('failures', 0)+1\n"
        "        if label == 'codex':\n"
        "            from standby import sync_health\n"
        "            sync_health(online, failures)\n")
    ast.parse(source);return source


def harness(source):
    source="import { standbyPrivate } from './standby-private.js';\n"+source
    anchor='        // T1 (PR port): 引用即叫/@全体即叫 开关与唤醒词门。mentionOpts 传给'
    seam=("        const standbyReply = await standbyPrivate(inbound, this.ctx.selfId());\n"
        "        if (standbyReply !== null) {\n"
        "            await this.ctx.sendToChat(chatId, standbyReply);\n"
        "            return;\n"
        "        }\n")
    return once(source,anchor,seam+anchor)


def group(source):
    anchor="        cmd = text.strip().strip('。！!').lower()\n"
    source=once(source,anchor,"        from standby import group_reception\n"
        "        if group_reception(self, key, text, ACCOUNTS, OWNER, GROUP):\n"
        "            return True\n"+anchor)
    ast.parse(source);return source


def friends(source):
    anchor="                    parts=event.get('message',[])\n"
    source=once(source,anchor,
        "                    if user == api.OWNER:\n"
        "                        from standby import reply_if_active\n"
        "                        from pathlib import Path as StandbyPath\n"
        "                        cfg=json.loads(StandbyPath('/home/ubuntu/qq-codex/bridge/.private/config.json').read_text())\n"
        "                        hcfg=json.loads(StandbyPath('/home/ubuntu/qq-dsh/napcat-runtime/.private/bridge-config.json').read_text())\n"
        "                        actor='smallc' if bot==str(cfg['bot_qq']) else 'harness' if bot==str(hcfg['bot_qq']) else None\n"
        "                        if actor:\n"
        "                            incoming_text=''.join(s.get('data',{}).get('text','') for s in event.get('message',[]) if s.get('type')=='text')\n"
        "                            standby_reply=reply_if_active(incoming_text,actor)\n"
        "                            if standby_reply is not None:\n"
        "                                send(user,standby_reply)\n"
        "                                continue\n"+anchor)
    # The main smallc bridge handles owner model failures; friend histories stay isolated.
    source=once(source,"                        except Exception:\n                            answer='这会儿回复没接上，稍后再聊。'",
        "                        except Exception:\n"
        "                            if user==api.OWNER and actor=='smallc':\n"
        "                                from standby import State, reception\n"
        "                                State().failed('generation')\n"
        "                                answer=reception(text,actor,'model')\n"
        "                            else:\n"
        "                                answer='这会儿回复没接上，稍后再聊。'")
    source=once(source,"                    if voice:\n                        try: raw=audio(answer[:4000])",
        "                    if voice and not (user==api.OWNER and actor and reply_if_active(text,actor) is not None):\n                        try: raw=audio(answer[:4000])")
    ast.parse(source);return source


def notice(source):
    source = source.replace('\r\n', '\n')
    anchor="    result=api('harness','send_private_msg',"
    i=source.index('    text = ');j=source.index(anchor,i)
    source=source[:i]+("    from standby import State\n"
        "    text = ('小c的QQ连回来了，回话能力还在确认，我先继续值班。' if online and State().read().get('model_out') else\n"
        "            '小c回来啦，已经确认QQ恢复在线，可以继续找她聊天了。' if online else\n"
        "            '小c的QQ暂时掉线啦，大肥鱼在自己这个号替她看着，嘿嘿。陪你聊两句可以，有什么正事等她回来再说吧。')\n")+source[j:]
    ast.parse(source);return source


def images(source):
    anchor="    def submit(self, bot, event_key, prompt, kind='generate', message_id=None):\n"
    source=once(source,anchor,anchor+
        "        from standby import image_blocked\n"
        "        if image_blocked(bot, getattr(self, 'user', OWNER)):\n"
        "            raise ValueError('standby_no_new_jobs')\n")
    source=once(source,"                self.notify(job['bot'], FAILURES[code])",
        "                from standby import image_failure_message\n"
        "                self.notify(job['bot'], image_failure_message(job['bot'], getattr(self, 'user', OWNER), code) or FAILURES[code])")
    ast.parse(source);return source
