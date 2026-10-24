import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publisher", ROOT / "scripts/publish_news.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
ENV = dict(NEWS_TITRE="Été ' $(echo test)", NEWS_DESCRIPTION="Ligne 1\nLigne 2",
           NEWS_CATEGORIE="Annonce", NEWS_URL="https://example.com/article")


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.news = self.directory / "news.json"
        self.counter = self.directory / "counter.json"
        p.write_json(self.news, [])
        p.write_json(self.counter, {"lastId": 0})

    def test_publish_twice_and_preserve_unicode(self):
        p.publish(self.directory, ENV)
        p.publish(self.directory, ENV)
        saved = p.read_json(self.news)
        self.assertEqual([x["id"] for x in saved], [1, 2])
        self.assertEqual(saved[0]["titre"], ENV["NEWS_TITRE"])
        self.assertEqual(saved[0]["imageUrl"], "")
        self.assertEqual(p.read_json(self.counter)["lastId"], 2)

    def test_dry_run_preserves_bytes(self):
        before = self.news.read_bytes(), self.counter.read_bytes()
        p.publish(self.directory, ENV, True)
        self.assertEqual(before, (self.news.read_bytes(), self.counter.read_bytes()))

    def test_invalid_inputs_leave_data_untouched(self):
        for key, value in [("NEWS_TITRE", " "), ("NEWS_DESCRIPTION", ""),
                           ("NEWS_CATEGORIE", "Autre"), ("NEWS_URL", "javascript:alert(1)"),
                           ("NEWS_URL", "https://a:bad"), ("NEWS_URL", "https://u:p@a"),
                           ("NEWS_IMAGE_URL", "http://example.com/a")]:
            with self.subTest(key=key, value=value):
                before = self.news.read_bytes(), self.counter.read_bytes()
                with self.assertRaises(ValueError):
                    p.publish(self.directory, dict(ENV, **{key: value}))
                self.assertEqual(before, (self.news.read_bytes(), self.counter.read_bytes()))

    def test_corrupt_state_is_rejected(self):
        item = p.publish(self.directory, ENV)
        for news, counter in [({}, {"lastId": 1}), ([item, item], {"lastId": 1}),
                              ([dict(item, id=True)], {"lastId": 1}),
                              ([item], {"lastId": True}), ([item], {"lastId": -1}),
                              ([dict(item, publicationDate="2026-02-30")], {"lastId": 1})]:
            with self.subTest(news=news, counter=counter):
                with self.assertRaises(ValueError):
                    p.validate_state(news, counter)

    def test_stale_counter_and_reserved_ids(self):
        item = p.publish(self.directory, ENV)
        p.write_json(self.counter, {"lastId": 0})
        self.assertEqual(p.publish(self.directory, ENV)["id"], 2)
        p.write_json(self.counter, {"lastId": 20})
        self.assertEqual(p.publish(self.directory, ENV)["id"], 21)

    def test_failure_preserves_old_news_and_reserves_id(self):
        original = p.write_json
        def fail_news(path, data):
            if path == self.news:
                raise OSError("simulated failure")
            original(path, data)
        with patch.object(p, "write_json", side_effect=fail_news):
            with self.assertRaises(OSError):
                p.publish(self.directory, ENV)
        self.assertEqual(p.read_json(self.news), [])
        self.assertEqual(p.read_json(self.counter)["lastId"], 1)
        self.assertEqual(p.publish(self.directory, ENV)["id"], 2)

    def test_atomic_replace_failure_cleans_temporary(self):
        before = self.news.read_bytes()
        with patch.object(p.os, "replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                p.write_json(self.news, [1])
        self.assertEqual(self.news.read_bytes(), before)
        self.assertEqual(sorted(x.name for x in self.directory.iterdir()),
                         ["counter.json", "news.json"])

    def test_second_process_cannot_publish_under_lock(self):
        import os
        with p.publication_lock(self.directory):
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/publish_news.py"),
                 "--news-dir", str(self.directory)],
                env=dict(os.environ, **ENV), capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(p.read_json(self.news), [])
        self.assertEqual(p.read_json(self.counter)["lastId"], 0)

    def test_real_repository_state_is_compatible(self):
        p.validate_state(p.read_json(ROOT / "news/news.json"),
                         p.read_json(ROOT / "news/counter.json"))


if __name__ == "__main__":
    unittest.main()
