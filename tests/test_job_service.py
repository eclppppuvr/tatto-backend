import unittest
from uuid import uuid4

from app.domain.entities import JobStatus, JobType
from app.domain.errors import JobForbidden, JobNotFound
from app.services.jobs import QUEUE_BY_TYPE, JobService
from tests.fakes import FakeJobRepo, RecordingDispatcher


class JobServiceTests(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.repo = FakeJobRepo()
        self.dispatcher = RecordingDispatcher(log=self.log)
        self.svc = JobService(self.repo, self.dispatcher, commit=lambda: self.log.append("commit"))
        self.user = uuid4()

    def test_submit_creates_pending_job(self):
        job = self.svc.submit(self.user, JobType.EXTRACT_SKETCH, "raw/a.jpg")
        self.assertEqual((job.status, job.progress, job.retry_count), (JobStatus.PENDING, 0, 0))
        self.assertEqual(self.repo.get(job.id).input_ref, "raw/a.jpg")

    def test_commit_happens_before_dispatch(self):
        self.svc.submit(self.user, JobType.EXTRACT_SKETCH, "raw/a.jpg")
        self.assertEqual(self.log, ["commit", "dispatch"])

    def test_broker_down_keeps_job_pending_and_does_not_raise(self):
        self.dispatcher.fail = True
        with self.assertLogs("app.services.jobs", level="ERROR"):
            job = self.svc.submit(self.user, JobType.EXTRACT_SKETCH, "raw/a.jpg")
        self.assertEqual(self.repo.get(job.id).status, JobStatus.PENDING)

    def test_get_for_user(self):
        job = self.svc.create(self.user, JobType.TRY_ON, "x")
        self.assertEqual(self.svc.get_for_user(self.user, job.id).id, job.id)
        with self.assertRaises(JobForbidden):
            self.svc.get_for_user(uuid4(), job.id)
        with self.assertRaises(JobNotFound):
            self.svc.get_for_user(self.user, uuid4())

    def test_queues(self):
        self.assertEqual(QUEUE_BY_TYPE[JobType.EXTRACT_SKETCH], "cpu")
        self.assertEqual(QUEUE_BY_TYPE[JobType.GENERATE_DESIGN], "cpu")
        self.assertEqual(QUEUE_BY_TYPE[JobType.TRY_ON], "gpu")


if __name__ == "__main__":
    unittest.main()
