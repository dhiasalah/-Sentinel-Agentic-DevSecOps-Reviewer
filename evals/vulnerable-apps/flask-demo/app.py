# DELIBERATELY VULNERABLE: test target for Sentinel. Never run or deploy this.
import hashlib
import pickle
import sqlite3
import subprocess

from flask import Flask, request

app = Flask(__name__)
ADMIN_PASSWORD = "hunter2-not-a-real-secret"


@app.route("/user")
def get_user():
    user_id = request.args.get("id")
    conn = sqlite3.connect("app.db")
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return str(conn.execute(query).fetchall())


@app.route("/ping")
def ping():
    host = request.args.get("host")
    return subprocess.check_output(f"ping -c 1 {host}", shell=True)


@app.route("/load", methods=["POST"])
def load():
    return str(pickle.loads(request.data))


def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
