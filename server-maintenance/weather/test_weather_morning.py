from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import weather_morning as w

NOW = datetime(2026, 11, 18, 6, tzinfo=w.TZ)


def forecast():
    return {'timezone': 'Asia/Shanghai', 'daily': {'time': ['2026-11-18'],
            'temperature_2m_min': [10], 'temperature_2m_max': [20]},
            'hourly': {'time': [f'2026-11-18T{i:02}:00' for i in range(24)],
                       'precipitation_probability': [0]*24, 'precipitation': [0]*24}}


class WeatherTests(unittest.TestCase):
    def test_precipitation_uses_preceding_hour_and_partial_overlap(self):
        data = forecast()['hourly']
        data['precipitation_probability'][8] = 99  # 07:00-08:00 is outside commute.
        data['precipitation_probability'][9] = 65
        data['precipitation_probability'][10] = 80
        data['precipitation_probability'][11] = 100  # 10:00-11:00 is outside.
        self.assertIn('80%', w.commute(data, '2026-11-18', '08:30', '10:00'))
        data['precipitation_probability'][18] = 90  # Before evening commute.
        data['precipitation_probability'][19] = 10
        data['precipitation_probability'][20] = 95  # After evening commute.
        self.assertIn('10%', w.commute(data, '2026-11-18', '18:00', '19:00'))

    def test_missing_hour_is_rejected(self):
        data = forecast()['hourly']
        for values in data.values():
            values.pop(9)
        with self.assertRaises(ValueError):
            w.commute(data, '2026-11-18', '08:30', '10:00')

    def test_stale_day_is_rejected(self):
        with self.assertRaises(ValueError):
            w.render(forecast(), {}, NOW+timedelta(days=1))

    def test_missing_probability_is_not_treated_as_zero(self):
        data = forecast()
        data['hourly']['precipitation_probability'][9] = None
        with self.assertRaises(ValueError):
            w.render(data, {}, NOW)

    def test_metno_next_hour_conversion_no_invented_probability_and_cache(self):
        rows = []
        for hour in range(24):
            stamp = NOW.replace(hour=hour)
            rows.append({'time': stamp.isoformat(), 'data': {
                'instant': {'details': {'air_temperature': 15}},
                'next_1_hours': {'details': {'precipitation_amount': 1 if hour == 8 else 0}}}})
        payload = {'properties': {'meta': {'updated_at': datetime.now(w.TZ).isoformat()},
                                  'timeseries': rows}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(w, 'ROOT', Path(tmp)), \
                patch.object(w, 'fetch', return_value=payload) as fetch:
            data = w.metno_weather(NOW)
            text = w.render(data, {}, NOW)
            self.assertIn('08:30—10:00，预报有降水', text)
            self.assertIn('18:00—19:00，预报暂时没看到明显降水', text)
            self.assertNotIn('%', text)
            w.metno_weather(NOW)
            fetch.assert_called_once()

    def test_air_standard_and_estimated_nature_are_explicit(self):
        air = {'current': {'time': '2026-11-18T06:00', 'us_aqi': 110, 'pm2_5': 30}}
        text = w.render(forecast(), air, NOW)
        self.assertIn('美标AQI 110', text)
        self.assertIn('不是本地站点实测', text)
        self.assertIn('08:30—10:00', text)

    def test_stale_air_is_not_reported_as_current(self):
        air = {'current': {'time': '2026-11-17T06:00', 'us_aqi': 110, 'pm2_5': 30}}
        self.assertNotIn('110', w.air_line(air, NOW))

    def test_delivery_dedup_and_uncertain_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = w.State(Path(tmp)/'state.db')
            qq = Mock()
            qq.ready.return_value = True
            qq.send.side_effect = TimeoutError()
            self.assertEqual(w.deliver(state, NOW, 'preview', qq), 'uncertain')
            self.assertEqual(w.deliver(state, NOW, 'preview', qq), 'already_handled')
            qq.send.assert_called_once()
            state.db.close()

    def test_offline_preflight_can_retry_but_success_cannot_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = w.State(Path(tmp)/'state.db')
            qq = Mock()
            qq.ready.return_value = False
            self.assertEqual(w.deliver(state, NOW, 'preview', qq), 'queued')
            qq.send.assert_not_called()
            qq.ready.return_value = True
            qq.send.return_value = {'message_id': 123}
            self.assertEqual(w.deliver(state, NOW, 'preview', qq), 'sent')
            self.assertEqual(w.deliver(state, NOW, 'preview', qq), 'already_handled')
            state.db.close()

    def test_interrupted_sending_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'state.db'
            state = w.State(path)
            state.put(NOW.date().isoformat(), 'sending', NOW)
            state.db.close()
            state = w.State(path)
            self.assertEqual(state.get(NOW.date().isoformat()), 'uncertain')
            state.db.close()


if __name__ == '__main__':
    unittest.main()
