import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

scripts=Path(__file__).parents[1]/'skills/zhihu-daily/scripts'
sys.path.insert(0,str(scripts))
import pipeline
from daily import read,write,now


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.prefs=dict(english_level='CET-4',answer_target_words=[120,220],max_topics=10,answers_per_topic=2,
                        exclude_topics=[],prefer_topics=[],exclude_keywords=[],prefer_keywords=[],
                        delivery='html_attachment',recipient='test@example.com')
        write(self.root/'preferences.json',self.prefs)
        self.source={'fetched_at':now(),'items':[dict(id='12',title='Question',summary='Background',rank=1,categories=[],url='https://www.zhihu.com/question/12',answers=[dict(id='34',content='原文',author='名字',votes=30,url='https://www.zhihu.com/question/12/answer/34')])]}
        write(self.root/'output/sources.json',self.source)

    def edit_data(self):
        item=self.source['items'][0]
        return {'topics':{pipeline.topic_key(item,self.prefs):dict(title_en='Title',summary_en='Background',summary_zh='背景')},
                'answers':{pipeline.answer_key(item,item['answers'][0],self.prefs):dict(headline_en='What matters',paragraphs=[dict(en='I think practice matters.',zh='我认为练习很重要。')])}}

    def test_cache_hit_and_changed_source_invalidation(self):
        edits=self.edit_data();write(self.root/'output/edits.json',edits)
        with contextlib.redirect_stdout(io.StringIO()):pipeline.build(self.root,self.root/'output/edits.json',True)
        work,hits=pipeline.make_work(self.source,self.prefs,pipeline.load_cache(self.root))
        self.assertEqual(hits,dict(topics=1,answers=1));self.assertEqual(work['answers'],[])
        self.source['items'][0]['answers'][0]['content']='更新后的原文'
        work,hits=pipeline.make_work(self.source,self.prefs,pipeline.load_cache(self.root))
        self.assertEqual(hits,dict(topics=1,answers=0));self.assertEqual(len(work['answers']),1)

    def test_no_preference_skips_model_classification(self):
        def fake_api(endpoint,params):
            if endpoint=='hot_list':return {'Items':[dict(Title='Question',Summary='Background',Url='https://www.zhihu.com/question/12')]}
            return {'Items':[dict(Url='https://www.zhihu.com/question/12/answer/34',ContentText='原文',VoteUpCount=30)]}
        with patch.object(pipeline,'api',side_effect=fake_api),patch.object(pipeline.time,'sleep'),contextlib.redirect_stdout(io.StringIO()):pipeline.prepare(self.root)
        self.assertFalse((self.root/'output/classification-work.json').exists())
        self.assertEqual(read(self.root/'output/work-report.json')['new_answers'],1)

    def test_unknown_preference_pauses_before_answer_requests(self):
        self.prefs['exclude_topics']=['娱乐'];write(self.root/'preferences.json',self.prefs)
        with patch.object(pipeline,'api',return_value={'Items':[dict(Title='Question',Summary='',Url='https://www.zhihu.com/question/12')]}) as api,contextlib.redirect_stdout(io.StringIO()):pipeline.prepare(self.root)
        self.assertEqual(api.call_count,1)
        self.assertTrue((self.root/'output/classification-work.json').exists())

    def test_headline_rule_skips_network_and_language_work(self):
        self.prefs.update(headline_only_topics=['体育比赛'], topic_rules={'体育比赛':{'any':['乒乓球'],'context':['决赛']}})
        write(self.root/'preferences.json',self.prefs)
        hot={'Items':[dict(Title='乒乓球男单决赛，林诗栋4-0夺冠，如何评价本场比赛？',Summary='',Url='https://www.zhihu.com/question/12')]}
        with patch.object(pipeline,'api',return_value=hot) as api,contextlib.redirect_stdout(io.StringIO()):
            pipeline.prepare(self.root)
            work=read(self.root/'output/language-work.json')
            self.assertNotIn('summary',work['topics'][0])
            write(self.root/'output/edits.json',{'topics':{work['topics'][0]['key']:{'title_en':'Lin wins the table tennis final 4–0','title_zh':'林诗栋以4比0赢得乒乓球决赛'}},'answers':{}})
            pipeline.build(self.root,self.root/'output/edits.json',preview=True)
        self.assertEqual(api.call_count,1)
        work=read(self.root/'output/language-work.json')
        self.assertEqual(len(work['topics']),1)
        self.assertEqual(work['answers'],[])
        item=read(self.root/'output/digest.json')['items'][0]
        self.assertEqual(item['title_en'],'Lin wins the table tennis final 4–0')
        self.assertNotIn('如何评价',work['topics'][0]['title'])
        self.assertEqual(item['answers'],[])
        self.assertEqual(item['reading_depth'],'headline')

    def test_depth_invalidation_is_limited_to_preferred_topic(self):
        first=self.source['items'][0]
        other=dict(first,id='99',title='中美关税框架',categories=[])
        keys=[pipeline.answer_key(x,x['answers'][0],self.prefs) for x in (first,other)]
        self.prefs.update(prefer_topics=['中美经贸'],topic_rules={'中美经贸':{'any':['中美'],'context':['关税','贸易']}})
        self.assertEqual(keys[0],pipeline.answer_key(first,first['answers'][0],self.prefs))
        self.assertNotEqual(keys[1],pipeline.answer_key(other,other['answers'][0],self.prefs))
        work,_=pipeline.make_work(dict(items=[other]),self.prefs,pipeline.load_cache(self.root))
        self.assertEqual(work['answers'][0]['target_words'],[220,340])
        self.assertEqual(work['answers'][0]['reading_depth'],'deep')

    def test_offline_preferences_preserve_saved_sources(self):
        self.prefs['headline_only_keywords']=['Question']
        write(self.root/'preferences.json',self.prefs)
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline.prepare(self.root,offline=True)
            work=read(self.root/'output/language-work.json')
            write(self.root/'output/edits.json',{'topics':{work['topics'][0]['key']:{'title_en':'Headline','title_zh':'标题'}},'answers':{}})
            pipeline.build(self.root,self.root/'output/edits.json',preview=True)
        self.assertEqual(len(read(self.root/'output/sources.json')['items'][0]['answers']),1)
        self.assertEqual(read(self.root/'output/digest.json')['items'][0]['answers'],[])

    def test_headline_preference_overrides_deep_reading(self):
        self.prefs.update(headline_only_keywords=['Question'],prefer_keywords=['Question'])
        work,_=pipeline.make_work(self.source,self.prefs,pipeline.load_cache(self.root))
        self.assertEqual(work['answers'],[])
        self.assertEqual(work['topics'][0]['reading_depth'],'headline')

    def test_literal_style_invalidates_old_translation_cache(self):
        item=self.source['items'][0]
        old=pipeline.answer_key(item,item['answers'][0],self.prefs)
        self.prefs['translation_style']='literal-aligned-v1'
        self.assertNotEqual(old,pipeline.answer_key(item,item['answers'][0],self.prefs))

    def test_email_is_minimal_with_one_dated_html_attachment(self):
        edits=self.edit_data();write(self.root/'output/edits.json',edits)
        with contextlib.redirect_stdout(io.StringIO()):pipeline.build(self.root,self.root/'output/edits.json')
        output=io.StringIO()
        with contextlib.redirect_stdout(output):pipeline.mail(self.root)
        parts=json.loads(output.getvalue())['payload']['parts']
        self.assertEqual(len(parts),2)
        self.assertLess(len(parts[0]['body']['content']),350)
        self.assertNotIn('<h2',parts[0]['body']['content'])
        attachment=parts[1]
        self.assertEqual(attachment['content_disposition'],'attachment')
        self.assertEqual(attachment['filename'],'zhihu-daily-'+self.source['fetched_at'][:10]+'.html')
        self.assertIn(attachment['filename'],parts[0]['body']['content'])

    def test_preferred_order_survives_mail_validation(self):
        from preferences import apply_reading_preferences
        self.source['items'].append(dict(self.source['items'][0],id='56',title='Trade',rank=2,answers=[]))
        self.prefs['prefer_keywords']=['Trade']
        selected=apply_reading_preferences(self.source,self.prefs)
        self.assertEqual([x['id'] for x in selected['items']],['56','12'])
        self.assertEqual([x['id'] for x in self.source['items']],['12','56'])

    def test_reading_setting_invalidates_language_cache(self):
        item=self.source['items'][0];key=pipeline.answer_key(item,item['answers'][0],self.prefs)
        self.prefs['english_level']='A2'
        self.assertNotEqual(key,pipeline.answer_key(item,item['answers'][0],self.prefs))

    def test_classification_resume_does_not_refetch_the_hot_list(self):
        self.prefs['exclude_topics']=['娱乐'];write(self.root/'preferences.json',self.prefs)
        with patch.object(pipeline,'api',return_value={'Items':[dict(Title='Question',Summary='',Url='https://www.zhihu.com/question/12')]}) as api,contextlib.redirect_stdout(io.StringIO()):pipeline.prepare(self.root)
        work=read(self.root/'output/classification-work.json')
        write(self.root/'output/labels.json',{work['items'][0]['key']:[]})
        with contextlib.redirect_stdout(io.StringIO()):pipeline.import_labels(self.root,self.root/'output/labels.json')
        with patch.object(pipeline,'api',return_value={'Items':[]}) as api,patch.object(pipeline.time,'sleep'),contextlib.redirect_stdout(io.StringIO()):pipeline.prepare(self.root,resume=True)
        self.assertEqual(api.call_count,1)
        self.assertEqual(api.call_args.args[0],'zhihu_search')

    def test_excerpt_preserves_start_middle_end_and_discloses_omission(self):
        text='A'*100+'B'*100+'C'*100
        short,omitted=pipeline.source_excerpt(text,80)
        self.assertTrue(omitted);self.assertTrue(short.startswith('A'));self.assertTrue(short.endswith('C'));self.assertIn('B',short);self.assertIn('省略',short)

    def test_third_person_voice_is_rejected(self):
        edits=self.edit_data()
        next(iter(edits['answers'].values()))['paragraphs'][0]['en']='The author says practice matters.'
        write(self.root/'output/edits.json',edits)
        with self.assertRaisesRegex(ValueError,'Third-person'):pipeline.build(self.root,self.root/'output/edits.json',True)

    def test_preview_cannot_be_sent_as_fresh_daily(self):
        write(self.root/'output/build-report.json',dict(preview=True))
        with self.assertRaisesRegex(ValueError,'Preview'):pipeline.mail(self.root)

    def test_same_day_refresh_does_not_bypass_duplicate_delivery_check(self):
        edits=self.edit_data();write(self.root/'output/edits.json',edits)
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline.build(self.root,self.root/'output/edits.json')
            pipeline.mail(self.root)
        pending=read(self.root/'output/pending-delivery.json')
        pending['message_id']='sent123';write(self.root/'output/last-delivery.json',pending)
        import datetime as dt
        self.source['fetched_at']=dt.datetime.fromisoformat(self.source['fetched_at']).replace(microsecond=1).isoformat()
        write(self.root/'output/sources.json',self.source)
        with contextlib.redirect_stdout(io.StringIO()):pipeline.build(self.root)
        with self.assertRaisesRegex(ValueError,'already sent'):pipeline.mail(self.root)

    def test_partial_stage_survives_restart_and_repeated_import(self):
        edits = self.edit_data()
        path = self.root/'output/edits.json'
        write(path, {'topics':edits['topics']})
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline.stage(self.root,path)
            pipeline.stage(self.root,path)
        work = read(self.root/'output/language-batch.json')
        self.assertEqual(work['topics'],[])
        self.assertEqual(len(work['answers']),1)
        with self.assertRaisesRegex(ValueError,'Missing answer'):pipeline.build(self.root,preview=True)
        write(path, {'answers':edits['answers']})
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline.stage(self.root,path)
            self.assertEqual(read(self.root/'output/work-report.json')['status'],'ready_to_build')
            pipeline.build(self.root,preview=True)
        self.assertEqual(len(read(self.root/'output/digest.json')['items'][0]['answers']),1)

    def test_bad_stage_does_not_cache_any_part_of_batch(self):
        edits = self.edit_data()
        next(iter(edits['answers'].values()))['paragraphs'][0]['zh'] = ''
        path = self.root/'output/edits.json';write(path,edits)
        with self.assertRaisesRegex(ValueError,'both English and Chinese'):pipeline.stage(self.root,path)
        self.assertEqual(pipeline.load_cache(self.root)['topics'],{})
        edits = self.edit_data();edits['topics']['old-source'] = next(iter(edits['topics'].values()))
        write(path,edits)
        with self.assertRaisesRegex(ValueError,'Unexpected edit key'):pipeline.stage(self.root,path)
        self.assertEqual(pipeline.load_cache(self.root)['topics'],{})

    def test_batches_keep_all_tasks_whole_and_only_needed_questions(self):
        work = {'topics':[{'key':'t','title':'T'}],
                'answers':[{'key':str(i),'q':str(i),'text':'原文'*700} for i in range(4)],
                'questions':{str(i):'Question '+str(i) for i in range(4)}}
        seen=[]
        while work['topics'] or work['answers']:
            batch=pipeline.batch_work(work,1800)
            self.assertLessEqual(len(json.dumps(batch,ensure_ascii=False,separators=(',',':'))),1800)
            self.assertEqual(set(batch['questions']),{x['q'] for x in batch['answers']})
            for kind in ('topics','answers'):
                for task in batch[kind]:
                    self.assertIn(task,work[kind]);seen.append(task['key'])
                    work[kind].remove(task)
        self.assertEqual(seen,['t','0','1','2','3'])
        oversized={'topics':[],'answers':[{'key':'big','q':'1','text':'x'*9000}],'questions':{'1':'Q'}}
        self.assertEqual(pipeline.batch_work(oversized)['answers'],oversized['answers'])

    def test_fetch_error_blocks_language_and_resume_reuses_successes(self):
        hot={'Items':[dict(Title='Question '+qid,Summary='',Url='https://www.zhihu.com/question/'+qid) for qid in ('12','56')]}
        def fetch(endpoint,params):
            if endpoint=='hot_list':return hot
            if params['Query']=='Question 56':raise ValueError('Temporary network failure')
            return {'Items':[dict(Url='https://www.zhihu.com/question/12/answer/34',ContentText='原文',VoteUpCount=30)]}
        with patch.object(pipeline,'api',side_effect=fetch),patch.object(pipeline.time,'sleep'),contextlib.redirect_stdout(io.StringIO()):pipeline.prepare(self.root)
        report=read(self.root/'output/work-report.json')
        self.assertEqual(report['status'],'fetch_incomplete')
        self.assertEqual(report['fetch_failures'][0]['id'],'56')
        self.assertEqual(read(self.root/'output/language-batch.json')['topics'],[])
        with self.assertRaisesRegex(ValueError,'fetch incomplete'):pipeline.build(self.root,preview=True)
        with patch.object(pipeline,'api',return_value={'Items':[]}) as api,patch.object(pipeline.time,'sleep'),contextlib.redirect_stdout(io.StringIO()):pipeline.prepare(self.root,resume=True)
        self.assertEqual(api.call_count,1)
        self.assertEqual(api.call_args.args[1]['Query'],'Question 56')
        report=read(self.root/'output/work-report.json')
        self.assertEqual(report['status'],'language_needed')
        self.assertEqual(report['without_answers'],1)

    def test_cross_day_and_future_network_cache_are_not_reused(self):
        import datetime as dt
        stamp=dt.datetime(2026,10,1,0,1,tzinfo=dt.timezone(dt.timedelta(hours=8)))
        hot={'Items':[dict(Title='Question',Summary='',Url='https://www.zhihu.com/question/12')]}
        for offset in (-120,60):
            write(self.root/'.private/answer-fetch-cache.json',{'12':{'title':'Question','checked_at':stamp.timestamp()+offset,'answers':[]}})
            with patch.object(pipeline,'now',return_value=stamp.isoformat()),patch.object(pipeline.time,'time',return_value=stamp.timestamp()),patch.object(pipeline.time,'sleep'),patch.object(pipeline,'api',side_effect=[hot,{'Items':[]}]) as api,contextlib.redirect_stdout(io.StringIO()):pipeline.prepare(self.root)
            self.assertEqual(api.call_count,2)

    def test_legacy_success_and_no_match_are_not_fetch_errors(self):
        for status in ('ok','no_matching_answer','no_matching_answers'):
            self.source['items'][0]['answer_status']=status
            self.assertEqual(pipeline.fetch_failures(self.source,self.prefs),[])
        self.source['items'][0]['answer_status']='Zhihu HTTP 503; no automatic retry'
        self.assertEqual(len(pipeline.fetch_failures(self.source,self.prefs)),1)

    def build_for_mail(self):
        path=self.root/'output/edits.json';write(path,self.edit_data())
        with contextlib.redirect_stdout(io.StringIO()):pipeline.build(self.root,path)

    def test_pending_mail_blocks_retry_until_confirmed_unsent(self):
        self.build_for_mail()
        with contextlib.redirect_stdout(io.StringIO()):pipeline.mail(self.root)
        pending=read(self.root/'output/pending-delivery.json')
        with self.assertRaisesRegex(ValueError,'Pending delivery'):pipeline.mail(self.root)
        self.assertEqual(read(self.root/'output/pending-delivery.json'),pending)
        with self.assertRaisesRegex(ValueError,'mismatch'):pipeline.release_delivery(self.root,'wrong','Connector was not called')
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline.release_delivery(self.root,pending['delivery_key'],'Connector was not called')
            pipeline.mail(self.root)

    def test_delivery_history_remembers_older_editions_and_record_is_idempotent(self):
        self.build_for_mail()
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline.mail(self.root)
            pipeline.record_delivery(self.root,'messageA')
            pipeline.record_delivery(self.root,'messageA')
        self.assertFalse((self.root/'output/pending-delivery.json').exists())
        original=self.edit_data();changed=self.edit_data()
        next(iter(changed['topics'].values()))['title_en']='Updated title'
        path=self.root/'output/edits.json';write(path,changed)
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline.build(self.root,path)
            pipeline.mail(self.root)
            pipeline.record_delivery(self.root,'messageB')
        write(path,original)
        with contextlib.redirect_stdout(io.StringIO()):pipeline.build(self.root,path)
        with self.assertRaisesRegex(ValueError,'already sent'):pipeline.mail(self.root)
        self.assertEqual(len(pipeline.delivery_history(self.root)),2)

    def test_failed_delivery_record_preserves_reservation(self):
        self.build_for_mail()
        with contextlib.redirect_stdout(io.StringIO()):pipeline.mail(self.root)
        with patch.object(pipeline,'write',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):pipeline.record_delivery(self.root,'sent123')
        with self.assertRaisesRegex(ValueError,'Pending delivery'):pipeline.mail(self.root)
        with contextlib.redirect_stdout(io.StringIO()):pipeline.record_delivery(self.root,'sent123')
        self.assertFalse((self.root/'output/pending-delivery.json').exists())

    def test_legacy_confirmed_delivery_can_clear_its_old_reservation(self):
        pending={'delivery_key':'old-key','recipient':'test@example.com'}
        write(self.root/'output/pending-delivery.json',pending)
        write(self.root/'output/last-delivery.json',dict(pending,message_id='oldMessage',sent_at=now()))
        with contextlib.redirect_stdout(io.StringIO()):pipeline.record_delivery(self.root,'oldMessage')
        self.assertFalse((self.root/'output/pending-delivery.json').exists())
        self.assertEqual(read(self.root/'.private/delivery-history.json')['old-key']['message_id'],'oldMessage')

    def test_mail_regenerates_html_and_rejects_changed_build_inputs(self):
        self.build_for_mail()
        (self.root/'output/zhihu-daily.html').write_text('STALE HTML',encoding='utf-8')
        result=io.StringIO()
        with contextlib.redirect_stdout(result):pipeline.mail(self.root)
        self.assertNotIn('STALE HTML',result.getvalue())
        self.prefs['recipient']='changed@example.com';write(self.root/'preferences.json',self.prefs)
        with self.assertRaisesRegex(ValueError,'Build inputs changed'):pipeline.mail(self.root)

    def test_atomic_write_failure_preserves_previous_cache(self):
        import daily
        path=self.root/'cache.json';write(path,{'old':'complete'})
        with patch.object(daily.os,'replace',side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):write(path,{'new':'incomplete'})
        self.assertEqual(read(path),{'old':'complete'})
        self.assertEqual(list(self.root.glob('cache.json.*.tmp')),[])


if __name__=='__main__':unittest.main()
