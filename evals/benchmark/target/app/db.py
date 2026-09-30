import sqlite3


def find_user(conn: sqlite3.Connection, name: str):
    query = "SELECT id, email FROM users WHERE name = '%s'" % name
    return conn.execute(query).fetchone()


def find_user_by_email(conn: sqlite3.Connection, email: str):
    return conn.execute("SELECT id, name FROM users WHERE email = ?", (email,)).fetchone()
