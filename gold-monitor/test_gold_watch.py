from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import gold_watch as g

CONFIG = {'symbol': 'Au99.99', 'unit': 'CNY/g', 'lower': '810', 'upper': '890'}
HTML = '''<h1>上海黄金交易所2026年11月16日延时行情</h1><table>
<tr><th>合约</th><th>最新价</th><th>最高价</th><th>最低价</th><th>今开盘</th></tr>
<tr><td>iAu99.99</td><td>799.0</td></tr>
<tr><td>Au99.99</td><td><span>828.5</span></td><td>841</td><td>823</td><td>841</td></tr></table>'''


def quote(price):
    return dict(g.parse_quote(HTML), price=str(price))


class GoldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = g.State(Path(self.temp.name)/'state.db')

    def tearDown(self):
        self.state.db.close()
        self.temp.cleanup()

    def test_exact_instrument_latest_column_and_delayed_date(self):
        q = g.parse_quote(HTML)
        self.assertEqual(q['price'], '828.5')
        self.assertEqual(q['trade_date'], '2026-11-16')
        self.assertEqual(q['unit'], 'CNY/g')
        for body in [HTML.replace('Au99.99</td>', 'Au100g</td>'),
                     HTML.replace('828.5', '0'), HTML.replace('828.5', 'NaN'),
                     HTML.replace('2026年11月16日', '时间未知'), HTML.replace('最新价', '收盘价')]:
            with self.assertRaises(ValueError):
                g.parse_quote(body)

    def test_strict_thresholds_equal_values_do_not_trigger(self):
        for value, expected in [('809.99', 'below'), ('810', 'inside'), ('850', 'inside'), ('890', 'inside'), ('890.01', 'above')]:
            self.assertEqual(g.zone_for(value, '810', '890'), expected)
        with self.assertRaises(ValueError):
            g.zone_for('850', '890', '810')

    def test_old_or_future_quotes_do_not_look_current(self):
        q = quote(800)
        now = datetime(2026, 11, 17, 12, tzinfo=g.TZ)
        self.assertFalse(g.fresh_quote(q, now))
        self.assertTrue(g.fresh_quote(q, now-timedelta(days=1)))
        self.assertFalse(g.fresh_quote(q, now-timedelta(days=2)))
        q['trade_date'] = '2026-11-18'
        self.assertFalse(g.fresh_quote(q, now))
        self.assertTrue(g.fresh_quote(q, now.replace(hour=21)))

    def test_persistent_same_side_only_once_and_rearm_after_inside(self):
        first = self.state.observe(quote(809), CONFIG)
        self.assertIsNotNone(first)
        self.state.mark(first, 'sent', message_id=1)
        self.assertIsNone(self.state.observe(quote(805), CONFIG))
        self.state.db.close()
        self.state = g.State(Path(self.temp.name)/'state.db')
        self.assertIsNone(self.state.observe(quote(804), CONFIG))
        self.assertIsNone(self.state.observe(quote(810), CONFIG))
        second = self.state.observe(quote(808), CONFIG)
        self.assertGreater(second, first)

    def test_jump_to_opposite_side_creates_a_new_alert(self):
        first = self.state.observe(quote(800), CONFIG)
        second = self.state.observe(quote(900), CONFIG)
        self.assertNotEqual(first, second)
        self.assertEqual(self.state.db.execute('SELECT status FROM alerts WHERE id=?', (first,)).fetchone()[0], 'cancelled')

    def test_offline_keeps_pending_and_next_valid_check_refreshes_price(self):
        event = self.state.observe(quote(800), CONFIG)
        qq = Mock()
        qq.ready.return_value = False
        self.assertEqual(g.deliver(self.state, event, quote(800), CONFIG, qq), 'queued_qq_offline')
        qq.send.assert_not_called()
        self.assertEqual(self.state.observe(quote(803), CONFIG), event)
        qq.ready.return_value = True
        qq.send.return_value = {'message_id': 42}
        self.assertEqual(g.deliver(self.state, event, quote(803), CONFIG, qq), 'sent')
        self.assertIn('803 元/克', qq.send.call_args.args[0])
        self.assertIsNone(self.state.observe(quote(804), CONFIG))

    def test_back_inside_cancels_unsent_old_alert(self):
        event = self.state.observe(quote(800), CONFIG)
        self.state.mark(event, 'queued')
        self.assertIsNone(self.state.observe(quote(850), CONFIG))
        self.assertEqual(self.state.db.execute('SELECT status FROM alerts WHERE id=?', (event,)).fetchone()[0], 'cancelled')

    def test_uncertain_send_is_not_repeated_after_restart(self):
        event = self.state.observe(quote(900), CONFIG)
        qq = Mock()
        qq.ready.return_value = True
        qq.send.side_effect = TimeoutError()
        self.assertEqual(g.deliver(self.state, event, quote(900), CONFIG, qq), 'uncertain_no_retry')
        self.state.db.close()
        self.state = g.State(Path(self.temp.name)/'state.db')
        self.assertIsNone(self.state.observe(quote(901), CONFIG))

    def test_crash_in_sending_state_is_held_not_retried(self):
        event = self.state.observe(quote(900), CONFIG)
        self.state.mark(event, 'sending')
        self.state.db.close()
        self.state = g.State(Path(self.temp.name)/'state.db')
        self.assertEqual(self.state.db.execute('SELECT status FROM alerts WHERE id=?', (event,)).fetchone()[0], 'uncertain')
        self.assertIsNone(self.state.observe(quote(901), CONFIG))

    def test_ten_percent_inclusive_in_either_direction_inside_and_outside(self):
        first = self.state.observe(quote(800), CONFIG)
        self.state.mark(first, 'sent', message_id=1)
        self.assertIsNone(self.state.observe(quote('879.99'), CONFIG))
        up = self.state.observe(quote(880), CONFIG)
        qq = Mock()
        qq.send.return_value = {'message_id':2}
        self.assertEqual(g.deliver(self.state, up, quote(880), CONFIG, qq), 'sent')
        self.assertIn('上涨 10.00%', qq.send.call_args.args[0])
        self.assertIsNone(self.state.observe(quote(880), CONFIG))
        down = self.state.observe(quote(792), CONFIG)
        self.state.mark(down,'sent')
        self.assertIsNone(self.state.observe(quote('712.81'),CONFIG))
        self.assertIsNotNone(self.state.observe(quote('712.80'),CONFIG))

    def test_queued_move_cleared_after_rebound(self):
        first=self.state.observe(quote(800),CONFIG)
        self.state.mark(first,'sent')
        move=self.state.observe(quote(720),CONFIG)
        self.state.mark(move,'queued')
        self.assertIsNone(self.state.observe(quote(721),CONFIG))

    def test_atomic_partial_limit_updates(self):
        from gold_limits import limits
        folder=Path(self.temp.name)
        config=folder/'config.json'
        config.write_text(json.dumps(CONFIG))
        self.assertEqual(limits(folder,upper='920')['lower'],'810')
        self.assertEqual(limits(folder,lower='812.50')['upper'],'920')
        with self.assertRaises(ValueError):
            limits(folder,lower='930')
        self.assertEqual(limits(folder),{'lower':'812.50','upper':'920'})

    def test_notification_destination_cannot_be_set_by_quote_content(self):
        with patch.object(Path, 'read_text', return_value=json.dumps({
            'owner_qq': g.OWNER, 'bot_qq': g.BOT,
            'onebot_url': 'http://127.0.0.1:13001', 'onebot_token': 'test'})):
            qq = g.QQ()
        with patch.object(qq, 'request', return_value={'message_id': 1}) as call:
            qq.send('arbitrary quote text')
        self.assertEqual(call.call_args.args[0], 'send_private_msg')
        self.assertEqual(call.call_args.args[1]['user_id'], int(g.OWNER))
        text = g.alert_text(quote(809), 'below', CONFIG)
        self.assertIn('官方延时行情', text)
        self.assertIn('810', text)
        self.assertIn('抓取时间', text)


if __name__ == '__main__':
    unittest.main()
