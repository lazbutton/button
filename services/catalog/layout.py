"""Le rangement de la banque : le seul endroit du catalogue qui nomme ses dossiers.

Le moteur (engine/radiotomate/services/media_bank.py) et les scripts de la
station (deploy/scripts, deploy/share/apply_share.py) nomment les mêmes dossiers,
chacun à un seul endroit : test_layout.py les compare à cette liste. Le catalogue
ne lit pas tous ces dossiers, mais il les nomme tous, pour qu'il n'y ait qu'une
liste à laquelle se comparer.

Le rangement visé, et pourquoi : docs/decisions/0019-le-rangement-de-la-banque.md.
"""

from __future__ import annotations

# Les dossiers de tête de la banque.
INBOX = "00-inbox"
ROTATION = "10-rotation"
COLLECTIONS = "20-archives"
HABILLAGE = "30-habillage"
EMISSIONS = "40-emissions"
CARTS = "50-carts"
TRASH = "90-trash"
# Les liens vers le dossier de chaque bac, et la vue du dossier partagé.
CART_LINKS = "Carts"
VOLUME = ".volume"

# Les dossiers de l'habillage, et les deux dossiers d'une émission.
HABILLAGE_TYPES = ("jingles", "ids", "pubs", "beds", "stings", "sfx")
EMISSION_SLOTS = ("entiere", "podcasts")

# L'inbox range un dépôt d'après sa destination.
INBOX_ROTATION = f"{INBOX}/rotation"
INBOX_COLLECTIONS = f"{INBOX}/archives"
INBOX_HABILLAGE = f"{INBOX}/habillage"
INBOX_EMISSIONS = f"{INBOX}/emissions"
INBOX_SOURCES = f"{INBOX}/_sources"
INBOX_REJETS = f"{INBOX}/_rejets.json"

# Le regroupement Beets de la rotation, et l'identifiant de sa destination.
ROTATION_NAME = "rotation"

# La zone d'un fichier : ce que la recherche en dit sans nommer son dossier.
ZONES = {
    ROTATION: "rotation",
    COLLECTIONS: "collections",
    HABILLAGE: "habillage",
    EMISSIONS: "emissions",
    CARTS: "bacs",
}


def collection(name: str) -> str:
    return f"{COLLECTIONS}/{name}"


def inbox_collection(name: str) -> str:
    return f"{INBOX_COLLECTIONS}/{name}"


def habillage(kind: str) -> str:
    return f"{HABILLAGE}/{kind}"


def inbox_habillage(kind: str) -> str:
    return f"{INBOX_HABILLAGE}/{kind}"


def top_of(rel: str) -> str:
    return rel.split("/", 1)[0]


def zone_of(rel: str) -> str:
    """rotation, collections, habillage, emissions or bacs; empty anywhere else."""
    return ZONES.get(top_of(rel), "")


def habillage_of(rel: str) -> str:
    """The habillage folder a file is in, such as jingles or beds; empty anywhere else."""
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == HABILLAGE and parts[1] in HABILLAGE_TYPES:
        return parts[1]
    return ""
