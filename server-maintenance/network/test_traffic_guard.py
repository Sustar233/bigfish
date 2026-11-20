import unittest
from traffic_guard import account, choose


class TrafficTests(unittest.TestCase):
    def test_first_read_counts_already_used_bytes(self):
        self.assertEqual(account({},100,'2026-11-18')['used'],100)
    def test_repeated_cumulative_read_is_not_double_counted(self):
        a=account({},100,'2026-11-18')
        self.assertEqual(account(a,100,'2026-11-18')['used'],100)
        self.assertEqual(account(a,130,'2026-11-18')['used'],130)
    def test_restart_does_not_erase_today_usage(self):
        a={'day':'2026-11-18','used':100,'last_counter':100}
        self.assertEqual(account(a,20,'2026-11-18')['used'],120)
    def test_next_day_only_counts_new_counter_delta(self):
        a={'day':'2026-11-18','used':100,'last_counter':100}
        self.assertEqual(account(a,120,'2026-11-19')['used'],20)


    def test_new_process_counts_even_if_counter_exceeds_previous(self):
        a={'day':'2026-11-18','used':100,'last_counter':100,'generation':'old'}
        self.assertEqual(account(a,150,'2026-11-18','new')['used'],250)
    def test_primary_recovery_wins_over_daily_cap(self):
        self.assertEqual(choose(True,True,100,{'daily_backup_limit_bytes':100,'stop_margin_bytes':0})[0],'original')
    def test_cap_and_missing_accounting_stop_backup(self):
        p={'daily_backup_limit_bytes':100,'stop_margin_bytes':10}
        self.assertEqual(choose(False,True,89,p)[0],'backup')
        self.assertEqual(choose(False,True,90,p)[0],'blocked')
        self.assertEqual(choose(False,False,0,p)[0],'blocked')


if __name__=='__main__':unittest.main()
