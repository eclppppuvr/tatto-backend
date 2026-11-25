"""GET /v1/jobs/{id} и WS /v1/ws/jobs/{id}. Нужны зависимости из requirements-dev.txt."""
import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

try:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from starlette.websockets import WebSocketDisconnect
    import bcrypt  # noqa: F401
    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False

if HAVE_DEPS:
    from app.config import Settings
    from app.db.models import Base
    from app.db.repos import SqlJobRepo
    from app.domain.entities import Job, JobStatus, JobType
    from app.main import create_app

PASSWORD = "securePass123"
NOW = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)


@unittest.skipUnless(HAVE_DEPS, "не установлены зависимости из requirements-dev.txt")
class JobApiTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.app = create_app(Settings(db_url="sqlite://", jwt_secret="s" * 32, bcrypt_rounds=4), engine)
        self.client = TestClient(self.app)
        self.alice = self.register("alice@example.com")
        self.bob = self.register("bob@example.com")

    def register(self, email):
        r = self.client.post("/v1/auth/register", json={"email": email, "password": PASSWORD})
        return r.json()

    def make_job(self, owner, status=None, progress=45, **kw):
        status = status or JobStatus.RUNNING
        job = Job(uuid4(), UUID(owner["id"]), JobType.EXTRACT_SKETCH, status, progress,
                  "raw/x.jpg", kw.get("output_ref"), kw.get("error_code"), kw.get("error_message"), 0, NOW, NOW,
                  finished_at=NOW if status in (JobStatus.DONE, JobStatus.FAILED) else None)
        with self.app.state.session_factory() as s:
            SqlJobRepo(s).add(job)
            s.commit()
        return job

    @staticmethod
    def auth(user):
        return {"Authorization": f"Bearer {user['access_token']}"}

    # --- REST ---
    def test_get_job_contract(self):
        job = self.make_job(self.alice)
        r = self.client.get(f"/v1/jobs/{job.id}", headers=self.auth(self.alice))
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(set(body), {"id", "status", "progress", "output_ref", "error_code",
                                     "error_message", "created_at", "finished_at"})
        self.assertEqual((body["status"], body["progress"], body["output_ref"]), ("running", 45, None))

    def test_job_not_found_403_401(self):
        job = self.make_job(self.alice)
        self.assertEqual(self.client.get(f"/v1/jobs/{uuid4()}", headers=self.auth(self.alice)).status_code, 404)
        self.assertEqual(self.client.get(f"/v1/jobs/{job.id}", headers=self.auth(self.bob)).status_code, 403)
        self.assertEqual(self.client.get(f"/v1/jobs/{job.id}").status_code, 401)
        self.assertEqual(self.client.get("/v1/jobs/not-a-uuid", headers=self.auth(self.alice)).status_code, 422)

    # --- WebSocket ---
    def ws_close_code(self, url):
        with self.assertRaises(WebSocketDisconnect) as cm:
            with self.client.websocket_connect(url) as ws:
                ws.receive_text()
        return cm.exception.code

    def test_ws_bad_token(self):
        job = self.make_job(self.alice)
        self.assertEqual(self.ws_close_code(f"/v1/ws/jobs/{job.id}?token=junk"), 4401)
        self.assertEqual(self.ws_close_code(f"/v1/ws/jobs/{job.id}"), 4401)

    def test_ws_not_found_and_foreign(self):
        job = self.make_job(self.alice)
        self.assertEqual(self.ws_close_code(f"/v1/ws/jobs/{uuid4()}?token={self.alice['access_token']}"), 4404)
        self.assertEqual(self.ws_close_code(f"/v1/ws/jobs/{job.id}?token={self.bob['access_token']}"), 4403)

    def test_ws_finished_job_sends_final_event_and_closes(self):
        job = self.make_job(self.alice, status=JobStatus.DONE, progress=100, output_ref="sk_1")
        with self.client.websocket_connect(f"/v1/ws/jobs/{job.id}?token={self.alice['access_token']}") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg, {"type": "done", "job_id": str(job.id), "progress": 100,
                                   "status": "done", "message": None})
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_text()

    def test_ws_failed_job_event(self):
        job = self.make_job(self.alice, status=JobStatus.FAILED, progress=30, error_code="model_timeout",
                            error_message="AI-модель не ответила в течение 120 секунд")
        with self.client.websocket_connect(f"/v1/ws/jobs/{job.id}?token={self.alice['access_token']}") as ws:
            msg = ws.receive_json()
            self.assertEqual((msg["type"], msg["status"], msg["progress"]), ("error", "failed", 30))
            self.assertIn("120", msg["message"])


if __name__ == "__main__":
    unittest.main()
