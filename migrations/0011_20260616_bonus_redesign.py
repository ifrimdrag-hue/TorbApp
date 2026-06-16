"""
Migration 0011 — bonus module redesign schema.

Formalizeaza tabelele bonus (create anterior ad-hoc, doar in data/torb.db) in
runner-ul versionat, ca testele si deploy-urile noi sa le aiba. Idempotent.

Creeaza (IF NOT EXISTS): bonus_config, bonus_lunar_config,
        bonus_obiective_strategice, bonus_payout_grid, bonus_istoric
Adauga:  coloana realizat_manual pe bonus_obiective_strategice
Seed:    grila _default, cei 4 agenti de teren; sterge Teo daca exista.
"""

VERSION = 11
NAME = "0011_20260616_bonus_redesign"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bonus_config (
            agent_key   TEXT PRIMARY KEY,
            db_agent    TEXT,
            tip_agent   TEXT DEFAULT 'field',
            w_sales     REAL DEFAULT 0.45,
            w_margin    REAL DEFAULT 0.25,
            w_strategic REAL DEFAULT 0.30,
            gate_sales  REAL DEFAULT 0.80,
            gate_margin REAL DEFAULT 0.80,
            growth_pct  REAL DEFAULT 0.20,
            activ       INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS bonus_lunar_config (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            an            INTEGER NOT NULL,
            luna          INTEGER NOT NULL,
            agent_key     TEXT NOT NULL,
            monthly_bonus REAL NOT NULL,
            pool_listari  REAL DEFAULT 0,
            w_sales       REAL,
            w_margin      REAL,
            w_strategic   REAL,
            gate_sales    REAL,
            gate_margin   REAL,
            growth_pct    REAL,
            UNIQUE(an, luna, agent_key)
        );

        CREATE TABLE IF NOT EXISTS bonus_obiective_strategice (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            an             INTEGER NOT NULL,
            luna           INTEGER NOT NULL,
            agent_key      TEXT NOT NULL,
            tip            TEXT NOT NULL,
            referinta      TEXT,
            target_valoare REAL,
            target_unitate TEXT DEFAULT 'ron',
            pondere        REAL DEFAULT 0,
            bonus_per_unit REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS bonus_payout_grid (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_key   TEXT NOT NULL,
            threshold   REAL NOT NULL,
            multiplier  REAL NOT NULL,
            UNIQUE(agent_key, threshold)
        );

        CREATE TABLE IF NOT EXISTS bonus_istoric (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            an             INTEGER NOT NULL,
            luna           INTEGER NOT NULL,
            agent_key      TEXT NOT NULL,
            lunar_data     TEXT,
            penalty_pct    REAL DEFAULT 0,
            grad_incasare  REAL DEFAULT 1.0,
            stare          TEXT DEFAULT 'deschis',
            inchis_la      TEXT,
            note           TEXT,
            UNIQUE(an, luna, agent_key)
        );
    """)

    # Coloana noua (idempotent — verifica inainte de ALTER)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bonus_obiective_strategice)")}
    if "realizat_manual" not in cols:
        conn.execute("ALTER TABLE bonus_obiective_strategice ADD COLUMN realizat_manual REAL")

    # Seed grila _default
    grid = [(0.0, 0.0), (0.80, 0.5), (0.95, 0.8), (1.00, 1.0),
            (1.02, 1.1), (1.10, 1.2), (1.20, 1.5)]
    for thr, mul in grid:
        conn.execute(
            "INSERT OR IGNORE INTO bonus_payout_grid (agent_key, threshold, multiplier) "
            "VALUES ('_default', ?, ?)", (thr, mul))

    # Seed cei 4 agenti de teren (idempotent)
    agents = [
        ("Claudiu", "BRINZA CLAUDIU",   0.45, 0.25, 0.30),
        ("Bogdan",  "DRAGNEA BOGDAN",   0.50, 0.25, 0.25),
        ("Oana",    "Oana Filip",       0.50, 0.20, 0.30),
        ("Ionut",   "CONSTANTIN IONUT", 0.50, 0.20, 0.30),
    ]
    for key, db_agent, ws, wm, wst in agents:
        conn.execute(
            "INSERT OR IGNORE INTO bonus_config "
            "(agent_key, db_agent, tip_agent, w_sales, w_margin, w_strategic, "
            " gate_sales, gate_margin, growth_pct, activ) "
            "VALUES (?, ?, 'field', ?, ?, ?, 0.80, 0.80, 0.20, 1)",
            (key, db_agent, ws, wm, wst))

    # Teo eliminat complet din toate tabelele bonus
    for tbl in ("bonus_config", "bonus_lunar_config",
                "bonus_obiective_strategice", "bonus_payout_grid", "bonus_istoric"):
        conn.execute(f"DELETE FROM {tbl} WHERE agent_key = 'Teo'")
