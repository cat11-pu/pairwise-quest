"""quest.core 的行为测试：任务链接取、推进、完成、失败、超时与互斥分支。"""

import unittest

from quest.core import Clock, QuestLog


class QuestCoreTest(unittest.TestCase):
    """覆盖正常链路、边界输入、异常输入、回滚与状态不变量。"""

    def test_chain_unlocks_and_finishes_in_registration_order(self):
        """前置完成之后后续任务才可接取，一路推进到最后。"""
        log = QuestLog()
        log.register("chop", duration=3, reward=2)
        log.register("carry", prereqs=("chop",), duration=4, reward=3)
        self.assertTrue(log.accept("chop"))
        self.assertEqual(log.add_progress("chop", 3), 3)
        self.assertTrue(log.complete("chop"))
        self.assertEqual(log.status("chop"), "completed")
        self.assertEqual(log.status("carry"), "available")
        self.assertTrue(log.accept("carry"))
        self.assertEqual(log.add_progress("carry", 4), 4)
        self.assertTrue(log.complete("carry"))
        self.assertEqual(log.status("carry"), "completed")
        self.assertEqual(log.points, 12)

    def test_every_prerequisite_must_be_finished_first(self):
        """两个前置只完成一个时，后续任务仍不可接取。"""
        log = QuestLog()
        log.register("gather", duration=3, reward=2)
        log.register("smelt", duration=3, reward=2)
        log.register("forge", prereqs=("gather", "smelt"), duration=4, reward=5)
        self.assertTrue(log.accept("gather"))
        self.assertEqual(log.add_progress("gather", 3), 3)
        self.assertTrue(log.complete("gather"))
        self.assertFalse(log.accept("forge"))
        self.assertEqual(log.status("forge"), "locked")
        self.assertTrue(log.accept("smelt"))
        self.assertEqual(log.add_progress("smelt", 3), 3)
        self.assertTrue(log.complete("smelt"))
        self.assertEqual(log.status("forge"), "available")
        self.assertTrue(log.accept("forge"))

    def test_a_running_quest_cannot_be_accepted_again(self):
        """进行中的任务再次接取必须被拒，进度与截止时刻不变。"""
        log = QuestLog()
        log.register("patrol", duration=6)
        self.assertTrue(log.accept("patrol"))
        self.assertEqual(log.add_progress("patrol", 2), 2)
        log.tick(2)
        self.assertFalse(log.accept("patrol"))
        self.assertEqual(log.progress_of("patrol"), 2)
        self.assertEqual(log.deadline_of("patrol"), 6)

    def test_only_one_branch_of_a_group_can_be_taken(self):
        """同一互斥组里只要有一条分支走过，其余分支就不能再接取。"""
        log = QuestLog()
        log.register("rescue_river", duration=3, group="rescue")
        log.register("rescue_hill", duration=3, group="rescue")
        self.assertTrue(log.accept("rescue_river"))
        self.assertFalse(log.accept("rescue_hill"))
        self.assertEqual(log.add_progress("rescue_river", 3), 3)
        self.assertTrue(log.complete("rescue_river"))
        self.assertFalse(log.accept("rescue_hill"))
        self.assertEqual(log.progress_of("rescue_hill"), 0)

    def test_progress_is_capped_at_the_quest_duration(self):
        """多次推进累计不得超过任务时长，满进度之后不再记入。"""
        log = QuestLog()
        log.register("haul", duration=8, reward=1)
        self.assertTrue(log.accept("haul"))
        self.assertEqual(log.add_progress("haul", 5), 5)
        self.assertEqual(log.add_progress("haul", 5), 3)
        self.assertEqual(log.progress_of("haul"), 8)
        self.assertEqual(log.add_progress("haul", 4), 0)
        self.assertEqual(log.progress_of("haul"), 8)

    def test_a_quest_can_only_be_finished_with_full_progress(self):
        """进度没满的任务不能完成，补满之后才能完成。"""
        log = QuestLog()
        log.register("ritual", duration=8, reward=4)
        self.assertTrue(log.accept("ritual"))
        self.assertEqual(log.add_progress("ritual", 3), 3)
        self.assertFalse(log.complete("ritual"))
        self.assertEqual(log.status("ritual"), "active")
        self.assertEqual(log.progress_of("ritual"), 3)
        self.assertEqual(log.add_progress("ritual", 5), 5)
        self.assertTrue(log.complete("ritual"))
        self.assertEqual(log.status("ritual"), "completed")

    def test_a_quest_times_out_exactly_at_its_deadline(self):
        """到截止时刻仍未完成的任务立刻超时，进度与积分一并作废。"""
        log = QuestLog()
        log.register("watch", duration=5, reward=2)
        self.assertTrue(log.accept("watch"))
        self.assertEqual(log.add_progress("watch", 5), 5)
        self.assertEqual(log.points, 5)
        self.assertEqual(log.tick(5), ["watch"])
        self.assertEqual(log.status("watch"), "available")
        self.assertEqual(log.progress_of("watch"), 0)
        self.assertIsNone(log.deadline_of("watch"))
        self.assertEqual(log.timeouts, 1)
        self.assertEqual(log.points, 0)
        self.assertTrue(log.accept("watch"))

    def test_a_failed_quest_returns_to_its_previous_state(self):
        """主动失败后任务回到可接取状态，进度与截止时刻都清空。"""
        log = QuestLog()
        log.register("siege", duration=6, reward=2)
        self.assertTrue(log.accept("siege"))
        self.assertEqual(log.add_progress("siege", 4), 4)
        self.assertTrue(log.fail("siege"))
        self.assertEqual(log.status("siege"), "available")
        self.assertEqual(log.progress_of("siege"), 0)
        self.assertIsNone(log.deadline_of("siege"))
        self.assertEqual(log.failures, 1)
        self.assertFalse(log.fail("siege"))
        self.assertTrue(log.accept("siege"))
        self.assertEqual(log.deadline_of("siege"), 6)

    def test_progress_only_counts_for_a_running_quest(self):
        """没接取的任务既不产生进度也不产生积分。"""
        log = QuestLog()
        log.register("gate", duration=4)
        log.register("key", prereqs=("gate",), duration=4)
        log.register("idle", duration=4)
        self.assertEqual(log.available(), ["gate", "idle"])
        self.assertEqual(log.add_progress("key", 2), 0)
        self.assertEqual(log.add_progress("idle", 3), 0)
        self.assertEqual(log.progress_of("key"), 0)
        self.assertEqual(log.progress_of("idle"), 0)
        self.assertEqual(log.points, 0)

    def test_unknown_quest_and_bad_input_are_rejected(self):
        """未知任务与非法参数必须报错，而不是静默改动状态。"""
        log = QuestLog(clock=Clock())
        log.register("scout", duration=4)
        with self.assertRaises(KeyError):
            log.accept("missing")
        with self.assertRaises(KeyError):
            log.add_progress("missing", 1)
        with self.assertRaises(ValueError):
            log.add_progress("scout", 0)
        with self.assertRaises(ValueError):
            log.register("scout", duration=4)
        with self.assertRaises(KeyError):
            log.register("ranger", prereqs=("ghost",))
        with self.assertRaises(ValueError):
            log.register("ranger", duration=0)


if __name__ == "__main__":
    unittest.main()
