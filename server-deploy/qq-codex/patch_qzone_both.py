"""Small source-preserving patches to the existing group and DeepSeek adapter."""
import ast


def patch_group(source):
    anchor = 'from bridge import Bridge, model_reply, log\n'
    if source.count(anchor) != 1 or 'from qzone_group import handle_group_qzone' in source:
        raise ValueError('unexpected group imports')
    source = source.replace(anchor, anchor + 'from qzone_group import handle_group_qzone\n', 1)
    anchor = "        cmd = text.strip().strip('。！!').lower()\n"
    if source.count(anchor) != 1:
        raise ValueError('unexpected group admission layout')
    source = source.replace(anchor, anchor +
        '        if handle_group_qzone(self, key, text, mentions, OWNER, GROUP, ACCOUNTS, PRIVATE):\n'
        '            return True\n', 1)
    anchor = '；档案与记忆管理请私聊Codex。'
    if source.count(anchor) != 1:
        raise ValueError('unexpected group help layout')
    source = source.replace(anchor, '；/空间点赞 或“你们给我最新一条说说点赞”可让两位点赞，点名则只由对应账号执行；/空间状态 查看结果' + anchor, 1)
    ast.parse(source)
    return source


def patch_private(source):
    if "from './qzone-private.js'" in source:
        raise ValueError('qzone private hook already installed')
    anchor = '        // Route commands before media/quote expansion.'
    if source.count(anchor) != 1:
        raise ValueError('unexpected private command layout')
    seam = ("        // Explicit owner-only Qzone commands bypass model generation.\n"
            "        const qzoneReply = await handleQzoneInbound(inbound, this.ctx.selfId());\n"
            "        if (qzoneReply !== null) {\n"
            "            await this.ctx.sendToChat(chatId, qzoneReply);\n"
            "            return;\n"
            "        }\n")
    return "import { handleQzoneInbound } from './qzone-private.js';\n" + source.replace(anchor, seam + anchor, 1)
