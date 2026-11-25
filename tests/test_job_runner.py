import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.domain.entities import Job, JobStatus, JobType
from app.domain.errors import JobFailure, TransientJobError
from app.services.runner import JobRunner
from tests.fakes import FakeJobRepo, RecordingPublisher

NOW = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)


class FakeTimeout(Exception):
    pass


def make_job(status=JobStatus.PENDING, retry_count=0, job_type=JobType.EXTRACT_SKETCH):
    return Job(uuid4(), uuid4(), job_type, status, 0, "raw/x.jpg", None, None, None, retry_count, NOW, NOW)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.repo, self.pub = FakeJobRepo(), RecordingPublisher()
        self.commits = 0

    def commit(self):
        self.commits += 1

    def runner(self, handler, **kw):
        return JobRunner(self.repo, self.pub, {JobType.EXTRACT_SKETCH: handler}, commit=self.commit,
                         clock=lambda: NOW, timeout_exceptions=(FakeTimeout,), **kw)

    def add(self, **kw):
        return self.repo.add(make_job(**kw))

    def test_success_sets_done_and_output(self):
        job = self.add()
        out = self.runner(lambda ctx: "sk_123").run(job.id)
        self.assertEqual(out.status, "done")
        self.assertEqual((job.status, job.progress, job.output_ref), (JobStatus.DONE, 100, "sk_123"))
        self.assertEqual(job.started_at, NOW)
        self.assertEqual(job.finished_at, NOW)
        self.assertEqual(self.pub.events[-1]["type"], "done")
        self.assertEqual(self.pub.events[0]["status"], "running")

    def test_progress_is_monotonic_and_capped_below_100(self):
        job = self.add()

        def handler(ctx):
            ctx.report(30); ctx.report(10); ctx.report(250)
            return "ref"

        self.runner(handler).run(job.id)
        progresses = [e["progress"] for e in self.pub.events]
        self.assertEqual(progresses, [0, 30, 99, 100])

    def test_commit_after_every_save(self):
        job = self.add()
        self.runner(lambda ctx: "ref").run(job.id)
        self.assertEqual(self.commits, self.repo.saves)

    def test_permanent_failure(self):
        job = self.add()
        out = self.runner(lambda ctx: (_ for _ in ()).throw(JobFailure("плохой файл", "bad_image"))).run(job.id)
        self.assertEqual(out.status, "failed")
        self.assertEqual((job.status, job.error_code, job.error_message), (JobStatus.FAILED, "bad_image", "плохой файл"))
        self.assertEqual(self.pub.events[-1], {"type": "error", "job_id": str(job.id), "progress": 0,
                                               "status": "failed", "message": "плохой файл"})

    def test_unknown_exception_hides_details(self):
        job = self.add()

        def boom(ctx):
            raise ValueError("secret path /etc/passwd")

        with self.assertLogs("app.services.runner", level="ERROR"):
            self.runner(boom).run(job.id)
        self.assertEqual(job.error_code, "internal_error")
        self.assertNotIn("secret", job.error_message)

    def test_timeout_maps_to_model_timeout_without_retry(self):
        job = self.add()

        def slow(ctx):
            raise FakeTimeout()

        out = self.runner(slow).run(job.id)
        self.assertEqual(out.status, "failed")
        self.assertEqual(job.error_code, "model_timeout")
        self.assertEqual(job.error_message, "AI-модель не ответила в течение 120 секунд")

    def test_transient_error_retries_with_backoff_then_fails(self):
        job = self.add()
        runner = self.runner(lambda ctx: (_ for _ in ()).throw(TransientJobError()))
        delays = []
        for _ in range(3):
            out = runner.run(job.id)
            self.assertEqual(out.status, "retry")
            self.assertEqual(job.status, JobStatus.PENDING)
            delays.append(out.retry_in)
        self.assertEqual(delays, [10, 30, 90])
        self.assertEqual(job.retry_count, 3)
        out = runner.run(job.id)
        self.assertEqual(out.status, "failed")
        self.assertEqual(job.error_code, "transient_error")

    def test_retry_then_success(self):
        job = self.add()
        calls = []

        def flaky(ctx):
            calls.append(1)
            if len(calls) == 1:
                raise TransientJobError()
            return "ok"

        runner = self.runner(flaky)
        self.assertEqual(runner.run(job.id).status, "retry")
        self.assertEqual(runner.run(job.id).status, "done")
        self.assertIsNone(job.error_code)

    def test_finished_job_is_skipped(self):
        for status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            job = self.add(status=status)
            called = []
            out = self.runner(lambda ctx: called.append(1) or "x").run(job.id)
            self.assertEqual((out.status, called), ("skipped", []))

    def test_unknown_job_is_skipped(self):
        self.assertEqual(self.runner(lambda ctx: "x").run(uuid4()).status, "skipped")

    def test_missing_handler_fails_job(self):
        job = self.add(job_type=JobType.TRY_ON)
        out = self.runner(lambda ctx: "x").run(job.id)
        self.assertEqual((out.status, job.error_code), ("failed", "not_implemented"))

    def test_redelivery_of_running_job_counts_as_attempt(self):
        job = self.add(status=JobStatus.RUNNING)
        self.assertEqual(self.runner(lambda ctx: "ok").run(job.id).status, "done")
        self.assertEqual(job.retry_count, 1)

    def test_redelivery_gives_up_after_max_retries(self):
        job = self.add(status=JobStatus.RUNNING, retry_count=3)
        out = self.runner(lambda ctx: "ok").run(job.id)
        self.assertEqual((out.status, job.error_code), ("failed", "worker_lost"))


if __name__ == "__main__":
    unittest.main()
