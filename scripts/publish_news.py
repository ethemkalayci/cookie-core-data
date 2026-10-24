"""Publication locale; les deux fichiers doivent être commités ensemble."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
CATEGORIES = {"Annonce", "Mise à jour", "Maintenance", "Événement"}


def read_json(path):
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} doit être un texte non vide.")
    return value.strip()


def https_url(value, field, optional=False):
    if optional and value == "":
        return value
    value = text(value, field)
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or any(c.isspace() or ord(c) < 32 for c in value)):
        raise ValueError(f"{field} doit être une URL HTTPS sans identifiants.")
    parsed.port
    return value


def new_fields(env):
    result = {
        "titre": text(env.get("NEWS_TITRE"), "titre"),
        "description": text(env.get("NEWS_DESCRIPTION"), "description"),
        "categorie": text(env.get("NEWS_CATEGORIE"), "categorie"),
        "imageUrl": https_url(env.get("NEWS_IMAGE_URL", "").strip(), "imageUrl", True),
        "url": https_url(env.get("NEWS_URL"), "url"),
    }
    if result["categorie"] not in CATEGORIES:
        raise ValueError("Catégorie inconnue.")
    return result


def validate_state(news, counter):
    if not isinstance(news, list):
        raise ValueError("news.json doit contenir une liste.")
    if (not isinstance(counter, dict) or type(counter.get("lastId")) is not int
            or counter["lastId"] < 0):
        raise ValueError("counter.json doit contenir un lastId entier positif ou nul.")
    ids = set()
    for item in news:
        if not isinstance(item, dict):
            raise ValueError("Chaque actualité doit être un objet.")
        identifier = item.get("id")
        if type(identifier) is not int or identifier <= 0 or identifier in ids:
            raise ValueError("ID invalide ou dupliqué.")
        ids.add(identifier)
        for field in ("titre", "description", "categorie"):
            text(item.get(field), field)
        https_url(item.get("url"), "url")
        https_url(item.get("imageUrl"), "imageUrl", True)
        date = text(item.get("publicationDate"), "publicationDate")
        if datetime.strptime(date, "%Y-%m-%d").date().isoformat() != date:
            raise ValueError("Date invalide.")
    return max(counter["lastId"], max(ids, default=0))


@contextmanager
def publication_lock(directory):
    # OS lock released on process death. Keep the file to avoid inode races.
    with (directory / ".publish-news.lock").open("a+b") as stream:
        stream.seek(0)
        stream.write(b"\0")
        stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def publish(directory, env, dry_run=False):
    fields = new_fields(env)
    with publication_lock(directory):
        news_path, counter_path = directory / "news.json", directory / "counter.json"
        news, counter = read_json(news_path), read_json(counter_path)
        identifier = validate_state(news, counter) + 1
        item = dict(fields, id=identifier, publicationDate=datetime.now(
            ZoneInfo("Europe/Brussels")).date().isoformat())
        if not dry_run:
            # Reserve ID first: interruption can leave a gap, never reuse an ID.
            write_json(counter_path, dict(counter, lastId=identifier))
            write_json(news_path, news + [item])
            if read_json(counter_path)["lastId"] != identifier or read_json(news_path)[-1] != item:
                raise ValueError("Vérification après écriture échouée.")
    print(f"{'Simulation' if dry_run else 'Publication locale'} : ID {identifier}")
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--news-dir", type=Path, default=BASE_DIR / "news")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        publish(args.news_dir, os.environ, args.dry_run)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Publication refusée : {error}\n")


if __name__ == "__main__":
    main()
