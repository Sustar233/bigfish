import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

const exec = promisify(execFile);
const price = '[0-9]{1,6}(?:\\.[0-9]{1,2})?';
const unit = '(?:元(?:/克|每克)?)?';
const set = '(?:设置为?|设为|设成|调到|调成|调整为|改到|改成|改为|为|到|是)?';
const field = new RegExp('^(上限|下限)' + set + '(' + price + ')' + unit, 'u');
const range = new RegExp('^(?:区间|范围|上下限)' + set + '(' + price + ')' + unit + '(?:到|至|~|-|和|、)(' + price + ')' + unit + '$','u');

export function parseGold(text) {
    const clean = text.normalize('NFKC').replace(/\s/g,'').replace(/[。！？?!]+$/u,'');
    const prefix = /^(?:(?:大肥鱼|肥鱼|请|帮我|麻烦你|把|将|设置|调整|修改|查看|看看|查询)[,，]*)*金价(?:预警|提醒|警报)?/u.exec(clean);
    if (!prefix) return null;
    const tail = clean.slice(prefix[0].length);
    if (/^(?:上下限|区间|范围|上限|下限)(?:是多少|多少|是什么|呢)?$/u.test(tail)) return {};
    const pair = range.exec(tail);
    if (pair) return {lower:pair[1], upper:pair[2]};
    let rest = tail;
    const values = {};
    while (rest) {
        const part = field.exec(rest);
        if (!part) return null;
        const key = part[1] === '上限' ? 'upper' : 'lower';
        if (key in values) return null;
        values[key] = part[2];
        rest = rest.slice(part[0].length);
        if (rest && !/^(?:[,，、]|和|并且|并)?(?:上限|下限)/u.test(rest)) return null;
        rest = rest.replace(/^(?:[,，、]|和|并且|并)/u,'');
    }
    return Object.keys(values).length ? values : null;
}

export async function goldReply(text, run = exec) {
    const values = parseGold(text);
    if (!values) return null;
    const args = ['/home/ubuntu/gold-watch/gold_limits.py'];
    for (const [key,value] of Object.entries(values)) args.push('--'+key,value);
    try {
        const {stdout} = await run('/usr/bin/python3',args,{timeout:60000});
        const result = JSON.parse(stdout);
        if (result.error) return '请用正数，下限要小于上限。原设置已保留。';
        return '金价预警下限 '+result.lower+' 元/克，上限 '+result.upper+' 元/克。'
            + (args.length>1 ? '下次检查起生效。' : '');
    } catch {
        return '暂时没能确认金价设置，可以再问我「金价预警上下限是多少」。';
    }
}
