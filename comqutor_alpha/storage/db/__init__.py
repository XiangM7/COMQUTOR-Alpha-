"""Real (non-file) persistence for Week 3: ``alpha_matches`` and ``structure_graphs``.

Backed by SQLAlchemy Core against PostgreSQL in production and SQLite in
offline/test contexts, through the exact same repository contract (see
``repository.py``). Database configuration is read only from the server
environment (``COMQUTOR_DATABASE_URL``); it is never accepted from an HTTP
request.
"""

from __future__ import annotations
