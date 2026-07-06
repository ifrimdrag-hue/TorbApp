"""Migration 0027 - potential articles (owner request 2026-07-06).

produse.potential = 1 marks an article that is not (yet) in stock: it comes
from a supplier's portfolio or from a new supplier's price offer, and exists
so the commercial team can price it for Romania and put it in client offers.
Flipping potential back to 0 turns it into a regular article.
"""
import sqlite3

VERSION = 27
NAME = "0027_20260707_potential_articles"


def up(conn):
    try:
        conn.execute("ALTER TABLE produse ADD COLUMN potential INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already present
