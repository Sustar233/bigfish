import contextlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import server_runner as runner


class ServerTests(unittest.TestCase):
    def test_codex_schema_covers_only_current_batch_keys(self):
        batch = {'topics': [{'key': 'headline', 'reading_depth': 'headline'},
                            {'key': 'topic', 'reading_depth': 'normal'}],
                 'answers': [{'key': 'answer'}]}
        schema = runner.work_schema(batch)
        self.assertEqual(schema['properties']['topics']['required'], ['headline', 'topic'])
        headline = schema['properties']['topics']['properties']['headline']
        self.assertEqual(headline['required'], ['title_en', 'title_zh'])
        self.assertFalse(headline['additionalProperties'])
        classification = runner.work_schema({'required_topics': ['sports'],
                                             'items': [{'key': 'one'}]})
        self.assertEqual(classification['properties']['one']['items']['enum'], ['sports'])

    def test_codex_child_does_not_inherit_source_mail_or_api_secrets(self):
        env = {name: 'test-secret' for name in ('ZHIHU_ACCESS_SECRET', 'SMTP_PASSWORD',
               'DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_ACCESS_TOKEN')}
        with patch.dict(os.environ, env):
            child = runner.codex_env()
        self.assertTrue(all(name not in child for name in env))

    def test_codex_is_default_and_never_falls_back_to_paid_api(self):
        with patch.dict(os.environ, {'LLM_PROVIDER': 'codex', 'DEEPSEEK_API_KEY': 'test'}), \
             patch.object(runner, 'call_codex', side_effect=ValueError('quota')) as call:
            with self.assertRaisesRegex(ValueError, 'quota'):
                runner.call_model('JSON', {})
            call.assert_called_once()

    def test_missing_or_extra_model_keys_are_rejected(self):
        batch = {'topics': [{'key': 'a'}], 'answers': []}
        runner.validate_batch(batch, {'topics': {'a': {}}, 'answers': {}})
        for edits in ({'topics': {}, 'answers': {}},
                      {'topics': {'a': {}, 'b': {}}, 'answers': {}}):
            with self.assertRaises(ValueError):
                runner.validate_batch(batch, edits)

    def test_smtp_sends_one_html_attachment_and_records_only_after_success(self):
        packet = {'to': 'reader@example.com', 'subject': 'Daily', 'payload': {'parts': [
            {'body': {'content': 'See attachment'}},
            {'body': {'content': '<html>daily</html>'}, 'filename': 'daily.html'}]}}
        client = MagicMock()
        client.send_message.return_value = {}
        env = {'SMTP_HOST': 'smtp.example.com', 'SMTP_USER': 'sender@example.com',
               'SMTP_PASSWORD': 'test-only', 'SMTP_PORT': '465'}
        with patch.dict(os.environ, env), patch.object(runner.smtplib, 'SMTP_SSL', return_value=client), \
             patch.object(runner, 'invoke', side_effect=[packet, None]) as invoke:
            runner.send_mail()
            msg = client.send_message.call_args.args[0]
            self.assertEqual(len(list(msg.iter_attachments())), 1)
            self.assertEqual(next(msg.iter_attachments()).get_filename(), 'daily.html')
            self.assertIs(invoke.call_args_list[-1].args[0], runner.pipeline.record_delivery)

    def test_uncertain_smtp_failure_never_records_success(self):
        packet = {'to': 'reader@example.com', 'subject': 'Daily', 'payload': {'parts': [
            {'body': {'content': 'See attachment'}},
            {'body': {'content': '<html>daily</html>'}, 'filename': 'daily.html'}]}}
        client = MagicMock()
        client.send_message.side_effect = TimeoutError('uncertain')
        env = {'SMTP_HOST': 'smtp.example.com', 'SMTP_USER': 'sender@example.com',
               'SMTP_PASSWORD': 'test-only', 'SMTP_PORT': '465'}
        with patch.dict(os.environ, env), patch.object(runner.smtplib, 'SMTP_SSL', return_value=client), \
             patch.object(runner, 'invoke', return_value=packet) as invoke:
            with self.assertRaises(TimeoutError):
                runner.send_mail()
            self.assertEqual(invoke.call_count, 1)


if __name__ == '__main__':
    unittest.main()
