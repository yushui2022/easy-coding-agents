import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from eca import automations
from eca.automations import Library, Runner, Scheduler


def rrule_daily(at="09:00", start=datetime(2026, 7, 5, 9, 0)):
    return automations.build_rrule("DAILY", at=at, start=start)


def fields(**overrides):
    base = {"name": "每日简报", "prompt": "汇总过去 24 小时的项目变化", "rrule": rrule_daily(),
            "project": str(Path.cwd()), "permission": "read_only"}
    base.update(overrides)
    return base


class Schedule(unittest.TestCase):
    def test_round_trip_keeps_the_clock_time(self):
        spec = automations.parse_rrule(rrule_daily("07:25"))
        self.assertEqual(spec["freq"], "DAILY")
        self.assertEqual(spec["byhour"], [7])
        self.assertEqual(spec["byminute"], [25])
        self.assertIn("07:25", automations.describe(spec))

    def test_weekday_preset_says_workdays(self):
        text = automations.build_rrule("WEEKLY", at="09:30", weekdays=[0, 1, 2, 3, 4])
        self.assertIn("BYDAY=MO,TU,WE,TH,FR", text)
        self.assertIn("工作日 09:30", automations.describe(automations.parse_rrule(text)))

    def test_hourly_and_minutely(self):
        hourly = automations.parse_rrule(automations.build_rrule("HOURLY", interval=2, at="09:15"))
        self.assertEqual(hourly["freq"], "HOURLY")
        self.assertEqual(hourly["interval"], 2)
        self.assertEqual(hourly["byminute"], [15])
        self.assertIn("每 2 小时", automations.describe(hourly))
        minutely = automations.parse_rrule(automations.build_rrule("MINUTELY", interval=10))
        self.assertEqual(minutely["freq"], "MINUTELY")
        self.assertIn("每 10 分钟", automations.describe(minutely))

    def test_rejects_invalid_schedules(self):
        for text, message in [
                ("RRULE:FREQ=DAILY", "DTSTART"),
                ("DTSTART:20260705T090000\nRRULE:FREQ=SECONDLY", "FREQ"),
                ("DTSTART:20260705T090000\nRRULE:FREQ=DAILY;BYDAY=MO", "BYDAY"),
                ("DTSTART:20260705T090000\nRRULE:FREQ=DAILY;BYHOUR=99", "BYHOUR"),
                ("DTSTART:20260705T090000\nRRULE:FREQ=HOURLY;BYHOUR=9", "HOURLY")]:
            with self.assertRaises(ValueError, msg=text):
                automations.parse_rrule(text)

    def test_next_occurrence_for_each_frequency(self):
        daily = automations.parse_rrule(rrule_daily("09:00"))
        self.assertEqual(automations.next_after(daily, datetime(2026, 7, 5, 8, 0)), datetime(2026, 7, 5, 9, 0))
        self.assertEqual(automations.next_after(daily, datetime(2026, 7, 5, 9, 0)), datetime(2026, 7, 6, 9, 0))
        weekly = automations.parse_rrule(automations.build_rrule("WEEKLY", at="08:00", weekdays=[2],
                                                                 start=datetime(2026, 7, 5, 8, 0)))
        # 2026-07-05 is a Sunday; the next Wednesday is 2026-07-08.
        self.assertEqual(automations.next_after(weekly, datetime(2026, 7, 5, 9, 0)), datetime(2026, 7, 8, 8, 0))
        hourly = automations.parse_rrule(automations.build_rrule("HOURLY", interval=3, at="09:20",
                                                                 start=datetime(2026, 7, 5, 9, 20)))
        self.assertEqual(automations.next_after(hourly, datetime(2026, 7, 5, 10, 0)), datetime(2026, 7, 5, 12, 20))
        minutely = automations.parse_rrule(automations.build_rrule("MINUTELY", interval=10,
                                                                   start=datetime(2026, 7, 5, 9, 0)))
        self.assertEqual(automations.next_after(minutely, datetime(2026, 7, 5, 9, 7)), datetime(2026, 7, 5, 9, 10))

    def test_one_shot_has_no_next_occurrence_after_it(self):
        once = automations.parse_rrule("DTSTART:20260705T090000\nRRULE:FREQ=DAILY;COUNT=1")
        self.assertEqual(automations.next_after(once, datetime(2026, 7, 5, 8, 0)), datetime(2026, 7, 5, 9, 0))
        self.assertIsNone(automations.next_after(once, datetime(2026, 7, 5, 9, 0)))
        self.assertEqual(automations.max_jitter(once), 0)
        self.assertIn("单次", automations.describe(once))


class Jitter(unittest.TestCase):
    def test_window_matches_the_rule_shape(self):
        self.assertEqual(automations.max_jitter(automations.parse_rrule(rrule_daily("09:00"))), 300)
        hourly_multi = automations.parse_rrule("DTSTART:20260705T090000\nRRULE:FREQ=HOURLY;BYMINUTE=0,30")
        self.assertEqual(automations.max_jitter(hourly_multi), 119)
        every_five = automations.parse_rrule(automations.build_rrule("MINUTELY", interval=5))
        self.assertEqual(automations.max_jitter(every_five), 0)

    def test_offset_is_deterministic_and_bounded(self):
        window = 300
        first = automations.jitter("abc", 1_780_000_000_000, "salt", window)
        second = automations.jitter("abc", 1_780_000_000_000, "salt", window)
        self.assertEqual(first, second)
        self.assertTrue(-window <= first <= window)
        others = {automations.jitter("abc", 1_780_000_000_000 + index * 86_400_000, "salt", window)
                  for index in range(50)}
        self.assertGreater(len(others), 10)

    def test_next_run_never_sits_in_the_past(self):
        automation = {"id": "x", "rrule": rrule_daily("09:00")}
        now = int(datetime(2026, 7, 5, 12, 0).timestamp() * 1000)
        planned = automations.next_run(automation, now, "salt")
        self.assertGreater(planned["next_run_at"], now)
        self.assertEqual(datetime.fromtimestamp(planned["next_run_nominal_at"] / 1000), datetime(2026, 7, 6, 9, 0))


class Records(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        self.library = Library(Path(self.tmp.name) / "automations")

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_load_list_delete(self):
        saved = self.library.save(fields())
        self.assertTrue(saved["id"])
        self.assertTrue((self.library.folder(saved["id"]) / "automation.toml").is_file())
        self.assertEqual([row["id"] for row in self.library.list()], [saved["id"]])
        self.assertIn("每天 09:00", self.library.list()[0]["schedule"])
        self.assertTrue(self.library.delete(saved["id"]))
        self.assertEqual(self.library.list(), [])

    def test_hand_edited_file_wins(self):
        saved = self.library.save(fields())
        path = self.library.folder(saved["id"]) / "automation.toml"
        text = path.read_text("utf-8").replace("每日简报", "改过的名字")
        path.write_text(text, "utf-8")
        self.assertEqual(self.library.load(saved["id"])["name"], "改过的名字")

    def test_pausing_clears_the_next_run(self):
        saved = self.library.save(fields())
        self.assertIsNotNone(self.library.load(saved["id"])["next_run_at"])
        self.library.save({"id": saved["id"], "status": "PAUSED"})
        self.assertIsNone(self.library.load(saved["id"])["next_run_at"])

    def test_validation_is_actionable(self):
        cases = [
            (fields(name=""), "name"),
            (fields(prompt="  "), "prompt"),
            (fields(project=str(Path(self.tmp.name) / "missing")), "does not exist"),
            (fields(permission="everything"), "permission"),
            (fields(notification="sometimes"), "notification"),
            (fields(rrule="nonsense"), "rrule"),
        ]
        for data, expected in cases:
            with self.assertRaises(ValueError) as error:
                self.library.save(data)
            self.assertIn(expected, str(error.exception))

    def test_history_and_memory_append(self):
        saved = self.library.save(fields())
        self.library.append_run(saved["id"], {"status": "succeeded", "started_at": 1})
        self.library.append_run(saved["id"], {"status": "failed", "started_at": 2})
        rows = self.library.history(saved["id"])
        self.assertEqual([row["status"] for row in rows], ["failed", "succeeded"])
        self.library.append_memory(saved["id"], "第一次运行的结论")
        self.assertIn("第一次运行的结论", self.library.memory(saved["id"]))


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def __call__(self, automation, *, trigger="scheduled"):
        self.calls.append((automation["id"], trigger))
        return {"status": "succeeded", "started_at": 0, "finished_at": 1, "trigger": trigger}


class Scheduling(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        self.library = Library(Path(self.tmp.name) / "automations")
        self.runner = FakeRunner()
        self.events = []
        self.clock = lambda: datetime(2026, 7, 5, 10, 0).timestamp()
        self.scheduler = Scheduler(self.library, self.runner, lambda event, data: self.events.append(event),
                                   clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def automation(self, **overrides):
        saved = self.library.save(fields(**overrides))
        return saved

    def make_due(self, automation_id, when=None):
        when = when if when is not None else int(self.clock() * 1000) - 60_000
        self.library.patch_state(automation_id, next_run_at=when, next_run_nominal_at=when)

    async def test_due_only_lists_active_finished_waiting(self):
        ready = self.automation()
        self.make_due(ready["id"])
        paused = self.automation(name="暂停的", status="PAUSED")
        self.make_due(paused["id"])
        future = self.automation(name="未来")
        self.library.patch_state(future["id"], next_run_at=int(self.clock() * 1000) + 600_000)
        ids = [row["id"] for row in self.scheduler.due()]
        self.assertEqual(ids, [ready["id"]])

    async def test_tick_runs_a_due_task_once_and_moves_it_forward(self):
        automation = self.automation()
        self.make_due(automation["id"])
        self.assertEqual(await self.scheduler.tick(), 1)
        await asyncio.sleep(0)
        self.assertEqual(self.runner.calls, [(automation["id"], "scheduled")])
        self.assertIn("automations", self.events)
        self.assertEqual(await self.scheduler.tick(), 0)
        moved = self.library.load(automation["id"])
        self.assertGreater(moved["next_run_at"], int(self.clock() * 1000))

    async def test_overdue_recurring_jumps_to_the_next_occurrence(self):
        automation = self.automation()
        self.make_due(automation["id"])
        planned = self.scheduler.plan(self.library.load(automation["id"]), int(self.clock() * 1000))
        nominal = datetime.fromtimestamp(planned["next_run_nominal_at"] / 1000)
        self.assertEqual(nominal, datetime(2026, 7, 6, 9, 0))

    async def test_overdue_one_shot_gets_no_next_run(self):
        once = "DTSTART:20260705T090000\nRRULE:FREQ=DAILY;COUNT=1"
        automation = self.automation(rrule=once)
        self.make_due(automation["id"])
        self.scheduler.plan(self.library.load(automation["id"]), int(self.clock() * 1000))
        self.assertIsNone(self.library.load(automation["id"])["next_run_at"])

    async def test_nothing_runs_twice_within_the_gap(self):
        automation = self.automation()
        self.make_due(automation["id"])
        await self.scheduler.tick()
        await asyncio.sleep(0)
        self.library.patch_state(automation["id"], last_run_at=int(self.clock() * 1000) - 1_000,
                                 next_run_at=int(self.clock() * 1000) - 1_000)
        self.assertEqual(await self.scheduler.tick(), 0)

    async def test_run_now_advances_a_stale_schedule_and_refuses_overlap(self):
        automation = self.automation()
        self.make_due(automation["id"])
        record = await self.scheduler.run_now(automation["id"])
        self.assertEqual(record["status"], "succeeded")
        self.assertEqual(self.runner.calls[-1], (automation["id"], "manual"))
        self.scheduler._inflight.add(automation["id"])
        with self.assertRaises(ValueError):
            await self.scheduler.run_now(automation["id"])

    async def test_a_crashed_run_is_recorded_as_interrupted(self):
        automation = self.automation()
        self.library.patch_state(automation["id"], last_status="running", last_run_at=1)
        self.scheduler._settle()
        self.assertEqual(self.library.history(automation["id"])[0]["status"], "interrupted")
        self.assertEqual(self.library.state(automation["id"])["last_status"], "interrupted")


class Prompt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("ECA_TEST_TMP", tempfile.gettempdir()))
        self.library = Library(Path(self.tmp.name) / "automations")
        self.runner = Runner(self.library)

    def tearDown(self):
        self.tmp.cleanup()

    def test_prompt_carries_identity_memory_and_policy(self):
        saved = self.library.save(fields())
        self.library.append_memory(saved["id"], "上次说过：构建时间 3 分 20 秒")
        automation = self.library.load(saved["id"])
        text = self.runner.prompt(automation)
        self.assertIn(f"Automation ID: {saved['id']}", text)
        self.assertIn("上次运行：从未", text)
        self.assertIn("只读", text)
        self.assertIn("构建时间 3 分 20 秒", text)
        self.assertIn(automation["prompt"], text)
        self.assertIn("无人值守", text)

    def test_a_failed_run_is_data_not_an_exception(self):
        automation = self.library.save(fields())
        broken = {**self.library.load(automation["id"]), "project": str(Path(self.tmp.name) / "gone")}
        record = asyncio.run(self.runner(broken))
        self.assertEqual(record["status"], "failed")
        self.assertIn("项目目录不存在", record["error"])
        self.assertEqual(self.library.history(automation["id"])[0]["status"], "failed")
        self.assertIn("failed", self.library.memory(automation["id"]))


if __name__ == "__main__":
    unittest.main()
