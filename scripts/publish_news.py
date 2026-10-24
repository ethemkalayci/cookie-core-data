
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# 1. Chemins des fichiers
BASE_DIR = Path(__file__).resolve().parent.parent
NEWS_DIR = BASE_DIR / "news"

NEWS_FILE = NEWS_DIR / "news.json"
COUNTER_FILE = NEWS_DIR / "counter.json"

# Fichiers de sortie pour les tests
TEST_NEWS_FILE = NEWS_DIR / "news_test.json"
TEST_COUNTER_FILE = NEWS_DIR / "counter_test.json"


# 2. Fonction de lecture JSON
def read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


# 3. Fonction d'écriture JSON
def write_json(path, data):
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            suffix=".tmp",
            delete=False
        ) as file:
            temporary_path = Path(file.name)

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

            file.write("\n")

        os.replace(temporary_path, path)

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


# 4. Charger les actualités existantes
news = read_json(NEWS_FILE)

if not isinstance(news, list):
    raise ValueError("news.json doit contenir une liste.")

print(f"Nombre d'actualités : {len(news)}")


# 5. Charger le compteur
counter = read_json(COUNTER_FILE)

if not isinstance(counter, dict):
    raise ValueError("counter.json doit contenir un objet.")

last_id = counter["lastId"]

if type(last_id) is not int or last_id < 0:
    raise ValueError("Le compteur est invalide.")


# 6. Vérifier les identifiants existants
existing_ids = set()

for item in news:
    current_id = item["id"]

    if type(current_id) is not int or current_id <= 0:
        raise ValueError("Une actualité possède un ID invalide.")

    if current_id in existing_ids:
        raise ValueError(f"ID dupliqué : {current_id}")

    existing_ids.add(current_id)


# 7. Calculer le prochain identifiant
next_id = max(
    last_id,
    max(existing_ids, default=0)
) + 1

print(f"Dernier ID enregistré : {last_id}")
print(f"Prochain ID disponible : {next_id}")


# 8. Informations provenant du formulaire GitHub Actions
titre = os.environ["NEWS_TITRE"].strip()
description = os.environ["NEWS_DESCRIPTION"].strip()
categorie = os.environ["NEWS_CATEGORIE"].strip()
image_url = os.environ.get("NEWS_IMAGE_URL", "").strip()
url = os.environ["NEWS_URL"].strip()



# 9. Générer la date
publication_date = datetime.now(
    ZoneInfo("Europe/Brussels")
).date().isoformat()


# 10. Construire l'actualité
new_item = {
    "imageUrl": image_url,
    "categorie": categorie,
    "titre": titre,
    "description": description,
    "publicationDate": publication_date,
    "url": url,
    "id": next_id
}

print("\nNouvelle actualité préparée :")
print(json.dumps(new_item, ensure_ascii=False, indent=2))


# 11. Ajouter l'actualité à la liste
news.append(new_item)


# 12. Actualiser le compteur
counter["lastId"] = next_id


# 13. Enregistrer dans les fichiers de test
# Écrire le compteur en premier évite de réutiliser
# un ID si la seconde écriture échoue.
write_json(TEST_COUNTER_FILE, counter)
write_json(TEST_NEWS_FILE, news)


# 14. Confirmer les résultats
saved_counter = read_json(TEST_COUNTER_FILE)
saved_news = read_json(TEST_NEWS_FILE)

if saved_counter["lastId"] != next_id:
    raise ValueError("Le compteur enregistré est incorrect.")

if saved_news[-1]["id"] != next_id:
    raise ValueError("L'actualité enregistrée est incorrecte.")

print("\nPublication de test terminée.")
print(f"Actualités enregistrées : {len(saved_news)}")
print(f"Dernier ID enregistré : {saved_counter['lastId']}")
print(f"Fichier actualités : {TEST_NEWS_FILE.name}")
print(f"Fichier compteur : {TEST_COUNTER_FILE.name}")
