"""Insert /今日 into current deployed adapters while retaining other command handlers."""
import re


def patch_bridge(source):
    body = ("        if text.strip() == '/今日':\n"
            "            from today import overview\n"
            "            return overview(self.config['bot_qq']), None\n")
    if body not in source:
        source, count = re.subn(r'(?m)^    def command\(self, text, key[^\n]*\):\n',
                                lambda match: match[0] + body, source)
        if count != 1:
            raise ValueError('unexpected private bridge command layout')
    anchor = "                        context['received_at'] = timestamp(received)\n"
    facts = ("                        from today import topics_for, conversation_facts\n"
             "                        topics = topics_for(text)\n"
             "                        if topics:\n"
             "                            context['本轮私聊参考资料'] = conversation_facts(topics, self.config['bot_qq'])\n")
    if facts not in source:
        if source.count(anchor) != 1:
            raise ValueError('unexpected private conversation layout')
        source = source.replace(anchor, anchor + facts)
    return source


def patch_harness(source):
    header = "import { handleTodayInbound } from './today-private.js';\n"
    seam = '        // Route commands before media/quote expansion.'
    body = ("        const todayReply = await handleTodayInbound(inbound, this.ctx.selfId());\n"
            "        if (todayReply !== null) {\n"
            "            await this.ctx.sendToChat(chatId, todayReply);\n"
            "            return;\n"
            "        }\n")
    if header in source and body in source:
        return source
    if header in source or source.count(seam) != 1:
        raise ValueError('unexpected OneBot command layout')
    return header + source.replace(seam, body + seam)
