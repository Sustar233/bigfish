"""Source-preserving seams for current native voice and image pipelines."""
import ast


def once(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise ValueError('unexpected_voice_image_seam: ' + anchor[:80])
    return source.replace(anchor, replacement, 1)


def patch_smallc(source):
    source = once(source, '                media_command = self.media.command(text)\n',
        "                voice_image_reply = None\n"
        "                if voice_input:\n"
        "                    from voice_image import voice_image_command\n"
        "                    voice_image_reply = voice_image_command(text, key, str(self.config['bot_qq']),\n"
        "                        image_count=incoming.get('image_count', 0), message_id=incoming.get('message_id'))\n"
        "                media_command = None if voice_image_reply is not None else self.media.command(text)\n")
    source = once(source, '                if media_command is not None:\n',
        '                if voice_image_reply is not None:\n'
        '                    reply, export_path = voice_image_reply, None\n'
        '                elif media_command is not None:\n')
    ast.parse(source)
    return source


def patch_dafeiyu(source):
    if "from './voice-image.js'" in source:
        raise ValueError('voice_image_already_installed')
    anchor = '        const imageReply = await handleImageInbound(inbound, this.ctx.selfId());'
    source = once(source, anchor,
        "        const voiceImageReply = await handleVoiceImageInbound(inbound, this.ctx.selfId(),\n"
        "            (action, data) => this.ctx.call(action, data));\n"
        "        if (voiceImageReply !== null) {\n"
        "            await this.ctx.sendToChat(chatId, voiceImageReply);\n"
        "            return;\n"
        "        }\n" + anchor)
    return "import { handleVoiceImageInbound } from './voice-image.js';\n" + source
