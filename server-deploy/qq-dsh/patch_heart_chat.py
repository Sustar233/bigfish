"""Build updated OneBot adapter sources from the current installed version."""
def patch_sources(j):
    files = {}
    def put(path, data):
        files[path] = data
    def sub(path, anchor, replacement, n=1):
        source = files.get(path, path.read_text())
        if source.count(anchor) != n:
            raise ValueError('Unexpected adapter layout: ' + path.name)
        files[path] = source.replace(anchor, replacement)
    p=j/'inbound.js'; s=p.read_text();put(p,"import {emotionalContext,rememberVoice} from './heart-chat.js';\n"+s)
    sub(p,'        const role = isAdmin',"""        const isVoice = kind === 'private' && inbound.media.some(ref=>ref.kind==='voice');
            let speech='';
            if (isVoice) {
                try {speech=(await this.ctx.call('fetch_ptt_text',{message_id:inbound.messageId}))?.text||'';} catch {}
                final += '\\n本轮由程序朗读最终回复，只输出要说的正文，不调用发送语音工具。';
            }
            if(kind==='private') final += await emotionalContext(inbound,this.ctx.selfId(),speech);
            const role = isAdmin""")
    sub(p,'        if (this.ctx.interceptBusyTurn !== undefined','        if(isVoice) rememberVoice(final);\n        if (this.ctx.interceptBusyTurn !== undefined')
    p=j/'bridge.js';put(p,"import {takeVoice} from './heart-chat.js';\n"+p.read_text())
    sub(p,'        chat.pendingTurnRoles.push(role);','        (chat.pendingVoice ??= []).push(takeVoice(text));\n        chat.pendingTurnRoles.push(role);')
    sub(p,'            chat.activeTurnRole = chat.pendingTurnRoles.shift()', '            chat.voiceReply = chat.pendingVoice?.shift() ?? false;\n            chat.activeTurnRole = chat.pendingTurnRoles.shift()')
    p=j/'interim.js'
    sub(p,'if (this.ctx.effectiveInterim(chatId)) {','if (!chat.voiceReply && this.ctx.effectiveInterim(chatId)) {',p.read_text().count('if (this.ctx.effectiveInterim(chatId)) {'))
    sub(p,'sendToChat(chatId, final, { queuable: true })','sendToChat(chatId, final, { queuable: true, conversational: true, voiceReply: chat.voiceReply })',2)
    p=j/'outbound.js';put(p,"import {voiceFile,bubbles} from './heart-chat.js';\n"+p.read_text())
    sub(p,'            let sentCard = false;',"""            const conversation=options.conversational && splitChatId(chatId).kind==='private';
                if(conversation && options.voiceReply && clean.trim()){
                    let file;
                    try{file=await voiceFile(stripMarkdown(clean));}catch{}
                    if(file){
                        const id=await this.sendMsg(chatId,[{type:'record',data:{file}}],options);
                        return id===undefined?ids:[...ids,id];
                    }
                }
                let sentCard = false;""")
    sub(p,'if (threshold > 0 && clean.length > threshold)', 'if (!conversation && threshold > 0 && clean.length > threshold)')
    a=files[p];i=a.index('                    const segments = defense ? splitAtSegments(plain)');k=a.index('                        ids.push(id);',i)+len('                        ids.push(id);')
    sub(p,a[i:k],"""                    for(const piece of conversation ? bubbles(plain) : [plain]){
                            const segments=defense?splitAtSegments(piece):[{type:'text',data:{text:piece}}];
                            const id=await this.sendMsg(chatId,segments,{...options,replyTo});
                            if(id!==undefined) ids.push(id);
                        }""")
    sub(j/'bridge.js','            chat.voiceReply = chat.pendingVoice?.shift() ?? false;',
        '            chat.voiceReply = chat.pendingVoice?.shift() ?? false;\n            chat.voiceReceipt = {};')
    sub(j/'interim.js','voiceReply: chat.voiceReply','voiceReply: chat.voiceReply, voiceAlreadySent: chat.voiceReceipt?.sent',2)
    sub(j/'outbound.js','                const id = await this.sendMsg(chatId, segments, {});',
        "                const turn = this.ctx.getChat(chatId);\n"
        "                const receipt = turn?.voiceReply && segments.some(s=>s.type==='record') ? turn.voiceReceipt : null;\n"
        "                const id = await this.sendMsg(chatId, segments, {});\n"
        "                if(receipt) receipt.sent=true;")
    sub(j/'outbound.js','if(conversation && options.voiceReply && clean.trim()){',
        'if(conversation && options.voiceReply && options.voiceAlreadySent) return ids;\n'
        '            if(conversation && options.voiceReply && clean.trim()){')
    return files
