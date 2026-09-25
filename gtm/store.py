"""SQLite persistence. One file, no server. Upserts on email."""
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    email TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    score INTEGER, tier TEXT, owner TEXT, stage TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS touches (
    email TEXT, step INTEGER, date TEXT, channel TEXT, subject TEXT, body TEXT,
    PRIMARY KEY (email, step)
);
CREATE TABLE IF NOT EXISTS suppression (
    value TEXT PRIMARY KEY, reason TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS signals (
    target TEXT, signal TEXT, at TEXT, PRIMARY KEY (target, signal, at)
);
CREATE TABLE IF NOT EXISTS sends (
    email TEXT, step INTEGER, owner TEXT, sent_on TEXT, PRIMARY KEY (email, step)
);
CREATE TABLE IF NOT EXISTS notified (
    email TEXT PRIMARY KEY, at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, email TEXT, kind TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

STAGES = ["new", "contacted", "replied", "meeting", "opportunity", "won", "lost"]
SENDABLE_STAGES = ("new", "contacted")  # anything later means a human is on it


class Store:
    def __init__(self, path="gtm.db"):
        # web.py hands the connection to its (single) server thread
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def upsert_leads(self, leads):
        with self.db:
            new = [l.email for l in leads if not self.db.execute(
                "SELECT 1 FROM leads WHERE email=?", (l.email,)).fetchone()]
            self.db.executemany("INSERT INTO events (email, kind) VALUES (?, 'created')", [(e,) for e in new])
            self.db.executemany(
                """INSERT INTO leads (email, data, score, tier, owner, stage) VALUES (?,?,?,?,?,?)
                   ON CONFLICT(email) DO UPDATE SET data=excluded.data, score=excluded.score,
                   tier=excluded.tier, owner=excluded.owner, updated_at=CURRENT_TIMESTAMP""",
                [(l.email, json.dumps(l.to_dict()), l.score, l.tier, l.owner, l.stage) for l in leads],
            )

    def save_touches(self, touches):
        with self.db:
            self.db.executemany(
                "INSERT OR REPLACE INTO touches VALUES (:email,:step,:date,:channel,:subject,:body)", touches)

    def set_stage(self, email, stage):
        if stage not in STAGES:
            raise ValueError(f"stage must be one of {STAGES}")
        with self.db:
            cur = self.db.execute("UPDATE leads SET stage=? WHERE email=?", (stage, email.lower()))
            if cur.rowcount == 0:
                raise KeyError(email)
            self.db.execute("INSERT INTO events (email, kind) VALUES (?,?)", (email.lower(), stage))

    def leads(self, tier=None):
        q, args = "SELECT * FROM leads", ()
        if tier:
            q, args = q + " WHERE tier=?", (tier,)
        return [self._record(r) for r in self.db.execute(q + " ORDER BY score DESC", args)]

    def lead(self, email):
        r = self.db.execute("SELECT * FROM leads WHERE email=?", (email.lower(),)).fetchone()
        return self._record(r) if r else None

    def peak_stages(self):
        """{email: furthest stage before won/lost} from the stage events set_stage records."""
        rank = {s: i for i, s in enumerate(STAGES[1:5], 1)}  # contacted..opportunity
        peaks = {}
        for email, kind in self.db.execute("SELECT email, kind FROM events"):
            if kind in rank and rank[kind] > rank.get(peaks.get(email), 0):
                peaks[email] = kind
        return peaks

    def first_event(self, kinds):
        """{email: earliest 'YYYY-MM-DD HH:MM:SS' UTC} over events of these kinds."""
        q = f"SELECT email, MIN(at) FROM events WHERE kind IN ({','.join('?' * len(kinds))}) GROUP BY email"
        return dict(self.db.execute(q, kinds).fetchall())

    def add_event(self, email, kind):
        with self.db:
            self.db.execute("INSERT INTO events (email, kind) VALUES (?,?)", (email.lower(), kind))

    @staticmethod
    def _record(row):
        """Lead JSON merged with the columns; columns win (stage/owner change after import)."""
        row = dict(row)
        return {**json.loads(row.pop("data")), **row}

    def touches_due(self, on_date):
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM touches WHERE date<=? ORDER BY date, email", (on_date,))]

    def open_touches(self, on_date):
        """Due touches still worth doing: not yet sent, and the lead is still new/contacted."""
        return [dict(r) for r in self.db.execute(
            f"""SELECT t.* FROM touches t JOIN leads l ON l.email = t.email
                LEFT JOIN sends s ON s.email = t.email AND s.step = t.step
                WHERE t.date <= ? AND s.email IS NULL AND l.stage IN {SENDABLE_STAGES}
                ORDER BY t.date, t.email""", (on_date,))]

    def suppress(self, value, reason=""):
        """value is an email or a bare domain."""
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO suppression (value, reason) VALUES (?,?)",
                            (value.strip().lower(), reason))

    def suppressed(self):
        return {r[0] for r in self.db.execute("SELECT value FROM suppression")}

    def clear_touches(self, email):
        with self.db:
            self.db.execute("DELETE FROM touches WHERE email=?", (email.lower(),))

    def add_signals(self, signals):
        """signals: iterable of (email_or_domain, signal, iso_at). Exact repeats are ignored."""
        with self.db:
            cur = self.db.executemany("INSERT OR IGNORE INTO signals VALUES (?,?,?)", signals)
        return cur.rowcount

    def signals(self):
        return [tuple(r) for r in self.db.execute("SELECT target, signal, at FROM signals")]

    def notified(self):
        return {r[0] for r in self.db.execute("SELECT email FROM notified")}

    def mark_notified(self, emails):
        with self.db:
            self.db.executemany("INSERT OR IGNORE INTO notified (email) VALUES (?)", [(e,) for e in emails])

    def record_send(self, email, step, owner, sent_on):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO sends VALUES (?,?,?,?)", (email, step, owner, sent_on))

    def sent_keys(self):
        return {(r[0], r[1]) for r in self.db.execute("SELECT email, step FROM sends")}

    def sends_on(self, day, owner):
        return self.db.execute("SELECT COUNT(*) FROM sends WHERE sent_on=? AND owner=?", (day, owner)).fetchone()[0]
