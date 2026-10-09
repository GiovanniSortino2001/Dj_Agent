"""SQLite catalog, content IDs, portable paths relative to catalog directory."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from .analysis import analyze


class Catalog:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS tracks (id TEXT PRIMARY KEY, path TEXT NOT NULL, analysis TEXT NOT NULL)')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def add(self, path, backend='auto'):
        path = Path(path).resolve()
        data = analyze(path, backend)
        h = hashlib.sha256()
        with path.open('rb') as f:
            for b in iter(lambda: f.read(1024*1024), b''):
                h.update(b)
        tid = h.hexdigest()[:20]
        rel = os.path.relpath(path, self.path.parent)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO tracks VALUES (?, ?, ?)', (tid, rel, json.dumps(data, allow_nan=False)))
        return self.get(tid)

    def get(self, tid):
        row = self.db.execute('SELECT id, path, analysis FROM tracks WHERE id=?', (tid,)).fetchone()
        if not row:
            raise ValueError(f'Brano non trovato: {tid}')
        return dict(id=row[0], path=row[1], **json.loads(row[2]))

    def all(self):
        return [self.get(row[0]) for row in self.db.execute('SELECT id FROM tracks ORDER BY id')]

    def audio_path(self, track):
        path = self.path.parent / track['path']
        h = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(1024*1024), b''):
                h.update(block)
        if h.hexdigest()[:20] != track['id']:
            raise ValueError('Audio modificato dopo scan: reimportare il brano e rigenerare il piano')
        return path
