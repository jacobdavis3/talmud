from pathlib import Path

from flask import Flask, jsonify, render_template, request

from matcher import normalize_hebrew
from talmud_db import DB_PATH, connect, get_sage, init_db, sage_aliases, search_sages, statements_for_sage

app = Flask(__name__)
DB_FILE = Path(DB_PATH)


def get_conn():
    conn = connect(DB_FILE)
    init_db(conn)
    return conn


@app.route("/")
def home():
    return render_template("index.html")


@app.get("/api/sages")
def api_sages():
    query = normalize_hebrew(request.args.get("q", ""))
    limit = min(max(int(request.args.get("limit", 25)), 1), 100)
    with get_conn() as conn:
        rows = search_sages(conn, query, limit=limit)
    return jsonify(
        {
            "items": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "generation": r["generation"],
                    "yeshiva": r["yeshiva"],
                }
                for r in rows
            ]
        }
    )


@app.get("/api/statements")
def api_statements():
    sage_id = request.args.get("sage_id", type=int)
    if not sage_id:
        return jsonify({"error": "Missing required query parameter: sage_id"}), 400

    limit = min(max(int(request.args.get("limit", 500)), 1), 2000)
    with get_conn() as conn:
        rows = statements_for_sage(conn, sage_id, limit=limit)

    return jsonify(
        {
            "items": [
                {
                    "id": r["id"],
                    "tractate": r["tractate"],
                    "daf": r["daf"],
                    "segment": r["segment"],
                    "text_he": r["text_he"],
                    "matched_aliases": (r["matched_aliases"] or "").split(","),
                }
                for r in rows
            ]
        }
    )


@app.get("/api/sage/<int:sage_id>")
def api_sage(sage_id: int):
    with get_conn() as conn:
        row = get_sage(conn, sage_id)
        if not row:
            return jsonify({"error": "Sage not found"}), 404
        aliases = sage_aliases(conn, sage_id)
    return jsonify(
        {
            "id": row["id"],
            "name": row["name"],
            "generation": row["generation"],
            "yeshiva": row["yeshiva"],
            "aliases": aliases,
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
