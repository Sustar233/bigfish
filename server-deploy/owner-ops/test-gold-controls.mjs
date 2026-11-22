import test from 'node:test';
import assert from 'node:assert/strict';
import {parseGold,goldReply} from './gold-controls.mjs';
test('parse only complete limit commands',()=>{
    assert.deepEqual(parseGold('把金价预警下限改成800，上限改成920'),{lower:'800',upper:'920'});
    assert.deepEqual(parseGold('金价预警上限调到930'),{upper:'930'});
    assert.deepEqual(parseGold('金价预警上下限是多少？'),{});
    assert.deepEqual(parseGold('调整金价预警区间为800到920'),{lower:'800',upper:'920'});
    for(const s of ['别把金价预警上限改成900','金价预警上限改成900后会怎样','金价预警上限900，下限','金价预警上限900元，下限-1']) assert.equal(parseGold(s),null);
});
test('validated fields reach fixed executable',async()=>{
    const reply=await goldReply('金价上限设为920',async(file,args)=>{
        assert.equal(file,'/usr/bin/python3');
        assert.deepEqual(args,['/home/ubuntu/gold-watch/gold_limits.py','--upper','920']);
        return {stdout:'{"lower":"810","upper":"920"}'};
    });
    assert.match(reply,/810.*920/);
});
