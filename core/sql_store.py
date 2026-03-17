import sqlite3


class SQLStore:

    def __init__(self, path):

        self.path = path

    def store(self, index):

        conn = sqlite3.connect(self.path)
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS elements (
            id INTEGER,
            name TEXT,
            type TEXT
        )
        """)

        for e in index.elements:

            cur.execute(
                "INSERT INTO elements VALUES (?, ?, ?)",
                (e.id, e.name, e.type)
            )

        conn.commit()
        conn.close()
