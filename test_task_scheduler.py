import unittest
from unittest.mock import patch

import task_scheduler as ts


class TaskSchedulerInjectionTests(unittest.TestCase):
    """
    update_crontab() used to build a shell command string with
    task_name/config_id interpolated into it and run it with
    shell=True. A task_name containing a double quote could break
    out of the embedded echo argument and run arbitrary commands at
    the moment a task was created or updated, and a task_name or
    config_id containing a newline could inject a whole extra cron
    line. These tests check both the quoting and the input
    validation that close those holes.
    """

    def setUp(self):
        patcher = patch.object(ts, "get_cron_jobs", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

        patcher = patch.object(ts, "backup_cron_jobs", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("task_scheduler.subprocess.run")
    def test_update_crontab_does_not_shell_out(self, mock_run):
        ts.update_crontab(["* * * * * echo hi # task_id=1"])
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], ["crontab", "-"])
        self.assertNotIn("shell", kwargs)
        self.assertIn("input", kwargs)

    def test_add_tasks_to_cron_rejects_newline_in_task_name(self):
        with self.assertRaises(ValueError):
            ts.add_tasks_to_cron(
                task_name="evil\n* * * * * touch /tmp/pwned",
                cron_time="* * * * *",
                config_ids=["1"],
                task_mode="strm_creation",
            )

    def test_add_tasks_to_cron_rejects_non_numeric_config_id(self):
        with self.assertRaises(ValueError):
            ts.add_tasks_to_cron(
                task_name="ok",
                cron_time="* * * * *",
                config_ids=["1; touch /tmp/pwned"],
                task_mode="strm_creation",
            )

    @patch("task_scheduler.subprocess.run")
    def test_add_tasks_to_cron_accepts_valid_input(self, mock_run):
        task_ids = ts.add_tasks_to_cron(
            task_name="nightly sync",
            cron_time="0 0 * * *",
            config_ids=["1", "2"],
            task_mode="strm_creation",
        )
        self.assertEqual(len(task_ids), 2)
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], ["crontab", "-"])


if __name__ == "__main__":
    unittest.main()
