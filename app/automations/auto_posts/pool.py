"""Pool de poze pentru postari automate.

Folder principal: data/photos-pool/
Folder pentru poze deja folosite (backup): data/photos-pool/_used/

API:
- list_available() → lista de poze disponibile (fara _used)
- pick_random() → o poza random din pool, sau None daca e gol
- move_to_used(filename) → muta poza in _used/ dupa aprobare
- get_path(filename) → calea absoluta catre poza
- save_upload(filename, bytes) → salveaza o poza incarcata din UI
"""

import random
import shutil
from datetime import datetime
from pathlib import Path


VALID_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
POOL_DIR = DATA_DIR / "photos-pool"
USED_DIR = POOL_DIR / "_used"


def _ensure_dirs() -> None:
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    USED_DIR.mkdir(parents=True, exist_ok=True)


def list_available() -> list[str]:
    """Lista poze disponibile (in radacina pool-ului, exclud _used/)."""
    _ensure_dirs()
    out = []
    for p in POOL_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in VALID_EXT:
            out.append(p.name)
    return sorted(out)


def count_available() -> int:
    return len(list_available())


def pick_random() -> str | None:
    avail = list_available()
    if not avail:
        return None
    return random.choice(avail)


def get_path(filename: str) -> Path:
    _ensure_dirs()
    safe = Path(filename).name  # strip dirs
    return POOL_DIR / safe


def read_bytes(filename: str) -> bytes:
    return get_path(filename).read_bytes()


def media_type_for(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/jpeg")


def move_to_used(filename: str) -> Path:
    """Muta poza in _used/. Daca exista deja un fisier cu acelasi nume,
    adauga timestamp ca sa nu suprascriem."""
    _ensure_dirs()
    src = get_path(filename)
    if not src.exists():
        raise FileNotFoundError(f"Poza nu exista in pool: {filename}")

    dest = USED_DIR / src.name
    if dest.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = USED_DIR / f"{src.stem}__{ts}{src.suffix}"

    shutil.move(str(src), str(dest))
    return dest


def save_upload(filename: str, data: bytes) -> str:
    """Salveaza poza in pool. Returneaza numele final (poate fi modificat
    daca exista deja un fisier cu acelasi nume)."""
    _ensure_dirs()
    safe = Path(filename).name
    ext = Path(safe).suffix.lower()
    if ext not in VALID_EXT:
        raise ValueError(f"Extensie nesuportata: {ext}. Accept: {', '.join(VALID_EXT)}")

    dest = POOL_DIR / safe
    if dest.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = POOL_DIR / f"{Path(safe).stem}__{ts}{ext}"

    dest.write_bytes(data)
    return dest.name
