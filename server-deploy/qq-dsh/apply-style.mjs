import fs from 'node:fs';
import { createRequire } from 'node:module';
const root='/home/ubuntu/.local/share/dsh-runtime/node_modules/.pnpm';
const folder=fs.readdirSync(root).find(x=>x.startsWith('yaml@'));
const yaml=createRequire(import.meta.url)(root+'/'+folder+'/node_modules/yaml');
const path='/home/ubuntu/.dsh/profiles/web/cordis.patch.yml';
const entries=yaml.parse(fs.readFileSync(path,'utf8'));
if(entries.some(x=>x.id==='qq-natural-preset'))throw new Error('Style already installed');
entries.push({insert:[{id:'qq-natural-preset',name:'@deepseek-ai/dsh-agent-preset',config:{
  id:'qq-natural-v3',name:'QQ 自然聊天',description:'QQ 接话风格；保留工具与权限规则',
  plugins:[{id:'qq-natural-persona',name:'/home/ubuntu/qq-dsh/qq_chat_persona.mjs'}],
}}]});
const c=entries.find(x=>x.id==='dsh-onebot').config;
c.agentPreset='qq-natural-v3';
fs.writeFileSync(path,yaml.stringify(entries));fs.chmodSync(path,0o600);
console.log('Registered scoped QQ natural-chat preset.');
