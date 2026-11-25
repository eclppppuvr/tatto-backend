import struct
import unittest
import zlib
from datetime import datetime, timezone
from uuid import uuid4

from app.ai.registry import get_engine
from app.ai.stub import blank_png
from app.domain.entities import Job, JobStatus, JobType
from app.services.events import channel_name, job_event
from app.storage import InMemoryStorage, KeyExists, raw_key, sketch_key

NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)


def job(status, progress=0, message=None):
    return Job(uuid4(), uuid4(), JobType.EXTRACT_SKETCH, status, progress, "x", None, None, message, 0, NOW, NOW)


class EventTests(unittest.TestCase):
    def test_event_mapping(self):
        self.assertEqual(job_event(job(JobStatus.PENDING))["type"], "progress")
        self.assertEqual(job_event(job(JobStatus.RUNNING, 60))["type"], "progress")
        done = job_event(job(JobStatus.DONE, 100))
        self.assertEqual((done["type"], done["message"]), ("done", None))
        err = job_event(job(JobStatus.FAILED, 30, "AI-модель не ответила"))
        self.assertEqual((err["type"], err["message"], err["status"]), ("error", "AI-модель не ответила", "failed"))
        self.assertEqual(job_event(job(JobStatus.CANCELLED))["type"], "error")

    def test_event_fields_match_spec(self):
        self.assertEqual(set(job_event(job(JobStatus.RUNNING))), {"type", "job_id", "progress", "status", "message"})

    def test_channel_name(self):
        self.assertEqual(channel_name("abc"), "job:channel:abc")


class StorageTests(unittest.TestCase):
    def test_keys_are_immutable(self):
        s = InMemoryStorage()
        s.put("raw/a.jpg", b"1", "image/jpeg")
        with self.assertRaises(KeyExists):
            s.put("raw/a.jpg", b"2", "image/jpeg")
        self.assertEqual(s.get("raw/a.jpg"), b"1")

    def test_key_builders(self):
        self.assertRegex(raw_key("png"), r"^raw/[0-9a-f-]{36}\.png$")
        self.assertNotEqual(raw_key(), raw_key())
        self.assertEqual(sketch_key("sk_1"), "sketches/sk_1.png")
        self.assertEqual(sketch_key("sk_1", thumbnail=True), "sketches/sk_1_thumb.jpg")


class StubEngineTests(unittest.TestCase):
    def test_blank_png_is_valid(self):
        data = blank_png(8, 4)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        w, h = struct.unpack(">II", data[16:24])
        self.assertEqual((w, h), (8, 4))
        idat_len = struct.unpack(">I", data[33:37])[0]
        raw = zlib.decompress(data[41:41 + idat_len])
        self.assertEqual(len(raw), 4 * (1 + 8 * 3))
        self.assertTrue(all(b == 255 for row in range(4) for b in raw[row * 25 + 1:(row + 1) * 25]))

    def test_registry(self):
        res = get_engine("stub").extract_sketch(b"anything")
        self.assertEqual((res.model, res.png[:4]), ("stub", b"\x89PNG"))
        with self.assertRaises(ValueError):
            get_engine("nope")


if __name__ == "__main__":
    unittest.main()
