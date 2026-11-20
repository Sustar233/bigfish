from datetime import datetime
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import usage_meter as m


class MeterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.patch=patch.object(m,'ROOT',Path(self.temp.name));self.patch.start()
    def tearDown(self):
        self.patch.stop();self.temp.cleanup()
    def test_only_completed_turn_usage_is_counted_not_other_snapshots(self):
        usage={'input_tokens':100,'cached_input_tokens':40,'output_tokens':15}
        stdout='\n'.join([json.dumps({'type':'other','usage':usage}),json.dumps({'type':'turn.completed','usage':usage})])
        self.assertEqual(m.parse_codex(stdout)['input_tokens'],100)
        self.assertIsNone(m.parse_codex('not JSON'))
    def test_cache_is_subset_for_codex_but_additive_in_harness_native_format(self):
        self.assertEqual(m.normalized({'input_tokens':100,'cached_input_tokens':40,'output_tokens':15},'codex')[:4],(100,40,0,15))
        self.assertEqual(m.normalized({'inputTokens':174,'cacheReadTokens':7552,'outputTokens':15,'totalTokens':7741},'deepseek')[:4],(7726,7552,0,15))
    def test_idempotent_import_and_shanghai_day_boundary(self):
        at=datetime(2026,11,16,16,30,tzinfo=m.timezone.utc).timestamp()
        for _ in range(2):m.record('news_monitor','codex',{'input_tokens':100,'output_tokens':15},at=at,call_id='same')
        db=m.connect()
        self.assertEqual(db.execute('SELECT day,input,output FROM calls').fetchall(),[('2026-11-17',100,15)])
        db.close()
    def test_missing_usage_is_nullable_and_report_exposes_missing_count(self):
        m.record('news_monitor','codex',None,'failed')
        db=m.connect();self.assertIsNone(db.execute('SELECT input FROM calls').fetchone()[0]);db.close()
        m.export_reports()
        text=(m.ROOT/'daily_totals.csv').read_text()
        self.assertIn('usage缺失次数',text);self.assertIn('金价监控,0,0,0,0,0,0,无模型调用',text)
    def test_command_and_return_contract_preserved(self):
        result=SimpleNamespace(returncode=0,stdout=json.dumps({'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':15}}))
        with patch.object(m.subprocess,'run',return_value=result) as run:
            self.assertIs(m.run_metered(['codex','exec','-'],project='news_monitor',capture_output=True),result)
        self.assertIn('--json',run.call_args.args[0])
        db=m.connect();self.assertEqual(db.execute('SELECT input+output FROM calls').fetchone()[0],115);db.close()
    def test_meter_storage_failure_does_not_break_business_call(self):
        result=SimpleNamespace(returncode=0,stdout='')
        with patch.object(m.subprocess,'run',return_value=result),patch.object(m,'record',side_effect=OSError('no space')):
            self.assertIs(m.run_metered(['codex','exec','-'],project='news_monitor'),result)


if __name__=='__main__':unittest.main()
