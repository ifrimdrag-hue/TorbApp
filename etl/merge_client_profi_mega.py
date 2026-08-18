"""Compat shim — logica a fost generalizată în `etl/client_merges.py`.

Profi Rom Food SRL → Mega Image SRL e acum o intrare în `CLIENT_MERGES`
(`app/business_constants.py`), aplicată la fiecare import, nu doar la rebuild.
Scriptul se păstrează pentru că rula manual; folosiți `client_merges` direct.

Usage:
    python etl/client_merges.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client_merges  # noqa: E402


def run(conn=None):
    return client_merges.run(conn)


if __name__ == "__main__":
    run()
