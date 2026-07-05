from flask import Flask, render_template
import psycopg2
import os

app = Flask(__name__)

# Pulled from ECS task definition environment variables / Secrets Manager.
# Falls back to localhost values so `python app.py` also works on your laptop.
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "studenthub")
DB_USER = os.environ.get("DB_USER", "dbadmin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_PORT = os.environ.get("DB_PORT", "5432")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT,
        connect_timeout=5,
    )


@app.route("/")
def home():
    db_status = "Not connected"
    try:
        conn = get_db_connection()
        conn.close()
        db_status = "Connected"
    except Exception as e:
        db_status = f"Connection failed: {e}"

    return render_template(
        "index.html",
        message="StudentHub is LIVE on AWS!",
        db_status=db_status,
    )


@app.route("/health")
def health():
    # Target group health check hits this — keep it fast and dependency-free.
    return {"status": "healthy"}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
