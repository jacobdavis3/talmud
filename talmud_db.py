import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List

from tractates import TRACTATE_MAX_DAF

DB_PATH = Path("data/talmud.sqlite3")
TRACTATE_ORDER = {name: idx for idx, name in enumerate(TRACTATE_MAX_DAF.keys(), start=1)}


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sages (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            generation TEXT,
            yeshiva TEXT
        );

        CREATE TABLE IF NOT EXISTS sage_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sage_id INTEGER NOT NULL REFERENCES sages(id) ON DELETE CASCADE,
            alias TEXT NOT NULL,
            alias_normalized TEXT NOT NULL,
            UNIQUE(sage_id, alias_normalized)
        );

        CREATE TABLE IF NOT EXISTS statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tractate TEXT NOT NULL,
            daf TEXT NOT NULL,
            segment INTEGER NOT NULL,
            text_he TEXT NOT NULL,
            text_he_normalized TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS statement_sages (
            statement_id INTEGER NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
            sage_id INTEGER NOT NULL REFERENCES sages(id) ON DELETE CASCADE,
            matched_alias TEXT NOT NULL,
            PRIMARY KEY(statement_id, sage_id, matched_alias)
        );

        CREATE INDEX IF NOT EXISTS idx_alias_norm ON sage_aliases(alias_normalized);
        CREATE INDEX IF NOT EXISTS idx_statement_text_norm ON statements(text_he_normalized);
        CREATE INDEX IF NOT EXISTS idx_stmt_sage ON statement_sages(sage_id);
        """
    )
    conn.commit()


def replace_sages(conn: sqlite3.Connection, sages: List[Dict], alias_rows: List[Dict]) -> None:
    conn.execute("DELETE FROM statement_sages")
    conn.execute("DELETE FROM statements")
    conn.execute("DELETE FROM sage_aliases")
    conn.execute("DELETE FROM sages")

    conn.executemany(
        "INSERT INTO sages(id, name, generation, yeshiva) VALUES(?, ?, ?, ?)",
        [
            (
                idx,
                str(s.get("name", "")).strip(),
                str(s.get("generation", "")).strip(),
                str(s.get("yeshiva", "")).strip(),
            )
            for idx, s in enumerate(sages, start=1)
        ],
    )

    conn.executemany(
        "INSERT INTO sage_aliases(sage_id, alias, alias_normalized) VALUES(?, ?, ?)",
        [(a["sage_id"], a["alias"], a["alias_normalized"]) for a in alias_rows],
    )
    conn.commit()


def insert_statements(conn: sqlite3.Connection, statements: Iterable[Dict]) -> int:
    inserted = 0
    for st in statements:
        cur = conn.execute(
            """
            INSERT INTO statements(tractate, daf, segment, text_he, text_he_normalized)
            VALUES(?, ?, ?, ?, ?)
            """,
            (st["tractate"], st["daf"], st["segment"], st["text_he"], st["text_he_normalized"]),
        )
        statement_id = cur.lastrowid
        conn.executemany(
            "INSERT OR IGNORE INTO statement_sages(statement_id, sage_id, matched_alias) VALUES(?, ?, ?)",
            [(statement_id, m["sage_id"], m["match"]) for m in st["mentions"]],
        )
        inserted += 1

    conn.commit()
    return inserted


def search_sages(conn: sqlite3.Connection, query_norm: str, limit: int = 25) -> List[sqlite3.Row]:
    if not query_norm:
        return conn.execute(
            "SELECT id, name, generation, yeshiva FROM sages ORDER BY name LIMIT ?", (limit,)
        ).fetchall()

    return conn.execute(
        """
        SELECT DISTINCT s.id, s.name, s.generation, s.yeshiva
        FROM sages s
        JOIN sage_aliases a ON a.sage_id = s.id
        WHERE a.alias_normalized LIKE ?
        ORDER BY s.name
        LIMIT ?
        """,
        (f"%{query_norm}%", limit),
    ).fetchall()


def get_sage(conn: sqlite3.Connection, sage_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, name, generation, yeshiva FROM sages WHERE id = ?",
        (sage_id,),
    ).fetchone()


def sage_aliases(conn: sqlite3.Connection, sage_id: int) -> List[str]:
    rows = conn.execute(
        "SELECT alias FROM sage_aliases WHERE sage_id = ? ORDER BY LENGTH(alias) DESC, alias",
        (sage_id,),
    ).fetchall()
    return [r["alias"] for r in rows]


def _parse_daf(daf: str) -> tuple[int, int]:
    s = str(daf or "").strip().lower()
    if len(s) < 2:
        return (0, 0)
    side = 1 if s.endswith("a") else 2 if s.endswith("b") else 0
    try:
        num = int(s[:-1])
    except ValueError:
        num = 0
    return (num, side)


def statements_for_sage(conn: sqlite3.Connection, sage_id: int, limit: int = 500) -> List[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT st.id, st.tractate, st.daf, st.segment, st.text_he,
               GROUP_CONCAT(DISTINCT ss.matched_alias) AS matched_aliases
        FROM statements st
        JOIN statement_sages ss ON ss.statement_id = st.id
        WHERE ss.sage_id = ?
        GROUP BY st.id
        LIMIT 5000
        """,
        (sage_id,),
    ).fetchall()
    return sorted(
        rows,
        key=lambda r: (
            TRACTATE_ORDER.get(r["tractate"], 9999),
            _parse_daf(r["daf"])[0],
            _parse_daf(r["daf"])[1],
            int(r["segment"]),
        ),
    )[:limit]
