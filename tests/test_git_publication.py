import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_publish_news import ENV, ROOT, p


class GitPublicationTests(unittest.TestCase):
    def test_rejected_push_recalculates_id_from_remote(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            def git(directory, *args, check=True):
                return subprocess.run(["git", "-C", str(directory), *args],
                                      capture_output=True, text=True, check=check)
            remote = base / "remote.git"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True,
                           capture_output=True)
            writer = base / "writer"
            subprocess.run(["git", "clone", str(remote), str(writer)], check=True,
                           capture_output=True)
            def configure(directory):
                git(directory, "config", "user.name", "Test")
                git(directory, "config", "user.email", "test@example.invalid")
            configure(writer)
            news = writer / "news"
            news.mkdir()
            p.write_json(news / "news.json", [])
            p.write_json(news / "counter.json", {"lastId": 0})
            git(writer, "add", "news")
            git(writer, "commit", "-m", "Initial")
            git(writer, "branch", "-M", "main")
            git(writer, "push", "origin", "main")
            other = base / "other"
            subprocess.run(["git", "clone", "-b", "main", str(remote), str(other)],
                           check=True, capture_output=True)
            configure(other)
            def commit(directory):
                p.publish(directory / "news", dict(ENV, NEWS_TITRE=directory.name))
                git(directory, "add", "--", "news/news.json", "news/counter.json")
                git(directory, "commit", "-m", "Actualité")
            commit(writer)
            commit(other)
            git(other, "push", "origin", "main")
            self.assertNotEqual(git(writer, "push", "origin", "main",
                                    check=False).returncode, 0)
            git(writer, "fetch", "origin", "main")
            git(writer, "reset", "--hard", "origin/main")
            commit(writer)
            git(writer, "push", "origin", "main")
            self.assertEqual([x["id"] for x in p.read_json(news / "news.json")], [1, 2])
            self.assertEqual(p.read_json(news / "counter.json")["lastId"], 2)
            self.assertEqual(git(writer, "diff", "HEAD", "--", "news/news.json",
                                 "news/counter.json").stdout, "")

