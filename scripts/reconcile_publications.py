#!/usr/bin/env python3
"""Operator-only reconciliation for ambiguous Binance Square publication attempts.

This tool never performs network requests and never submits or retries a post.
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import Database  # noqa: E402


UNRESOLVED = ("SUBMITTING", "PUBLICATION_UNKNOWN")


def _connect(db_path: str):
    # Initialize additive schema/migrations through the application's DB layer.
    database = Database(db_path)
    return database


def _print_row(row):
    print(json.dumps(dict(row), indent=2, sort_keys=True))


def list_unresolved(conn):
    rows = conn.execute(
        "SELECT id, coin_symbol, status, remote_post_id, share_link, http_status, "
        "error, created_at, updated_at FROM publication_attempts "
        "WHERE status IN ('SUBMITTING', 'PUBLICATION_UNKNOWN') ORDER BY id"
    ).fetchall()
    for row in rows:
        _print_row(row)
    if not rows:
        print("No unresolved publication attempts.")


def show_attempt(conn, attempt_id: int):
    row = conn.execute(
        "SELECT * FROM publication_attempts WHERE id = ?", (attempt_id,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"No publication attempt with id={attempt_id}")
    _print_row(row)


def reconcile(conn, args):
    if not args.note.strip() or not args.evidence.strip() or not args.operator.strip():
        raise SystemExit("--note, --evidence and --operator must be non-empty")

    if args.action == "confirm-published":
        if not args.remote_post_id.strip():
            raise SystemExit("--remote-post-id is required for confirm-published")
        target = "PUBLISHED_CONFIRMED"
    else:
        if not args.confirm_no_post_created:
            raise SystemExit(
                "Refusing: pass --confirm-no-post-created only after independently "
                "verifying that Binance did not create the post."
            )
        target = "FAILED_CONFIRMED"

    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM publication_attempts WHERE id = ?", (args.attempt_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"No publication attempt with id={args.attempt_id}")
        if row["status"] not in UNRESOLVED:
            raise ValueError(
                f"Attempt is terminal ({row['status']}); terminal states cannot be overwritten"
            )

        supplied_id = args.remote_post_id.strip() if target == "PUBLISHED_CONFIRMED" else ""
        existing_id = str(row["remote_post_id"] or "")
        if existing_id and supplied_id and existing_id != supplied_id:
            raise ValueError("Supplied remote ID conflicts with the ID already stored in ledger")
        final_id = supplied_id or existing_id
        if target == "PUBLISHED_CONFIRMED" and not final_id:
            raise ValueError("A verified remote post ID is required")

        conn.execute(
            """
            UPDATE publication_attempts
            SET status = ?, remote_post_id = COALESCE(?, remote_post_id),
                share_link = COALESCE(?, share_link),
                reconciliation_note = ?, reconciliation_evidence = ?,
                reconciled_by = ?, reconciled_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP, error = ?
            WHERE id = ? AND status IN ('SUBMITTING', 'PUBLICATION_UNKNOWN')
            """,
            (
                target, final_id or None, args.share_link.strip() or None,
                args.note.strip(), args.evidence.strip(), args.operator.strip(),
                f"Operator reconciliation: {target}", args.attempt_id,
            ),
        )
        changed = conn.execute("SELECT changes()").fetchone()[0]
        if changed != 1:
            raise ValueError("Concurrent reconciliation detected; no state changed")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    result = conn.execute(
        "SELECT id, coin_symbol, status, remote_post_id, share_link, "
        "reconciliation_note, reconciliation_evidence, reconciled_by, reconciled_at "
        "FROM publication_attempts WHERE id = ?", (args.attempt_id,)
    ).fetchone()
    _print_row(result)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Inspect/reconcile publication attempts. This tool never publishes."
    )
    parser.add_argument(
        "--db", default=os.getenv("DATABASE_PATH", "agent.db"),
        help="SQLite database path (default: DATABASE_PATH or agent.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List SUBMITTING and PUBLICATION_UNKNOWN attempts")

    show = sub.add_parser("show", help="Show one ledger row")
    show.add_argument("attempt_id", type=int)

    for name in ("confirm-published", "confirm-failed"):
        cmd = sub.add_parser(name)
        cmd.add_argument("attempt_id", type=int)
        cmd.add_argument("--operator", required=True, help="Human operator identifier")
        cmd.add_argument("--note", required=True, help="Reason for the manual decision")
        cmd.add_argument("--evidence", required=True, help="Evidence reference/description")
        cmd.add_argument("--share-link", default="")
        if name == "confirm-published":
            cmd.add_argument("--remote-post-id", required=True)
        else:
            cmd.add_argument(
                "--confirm-no-post-created", action="store_true",
                help="Explicitly acknowledge independent verification of no created post",
            )
    return parser


def main_cli():
    parser = build_parser()
    args = parser.parse_args()
    database = _connect(args.db)
    try:
        if args.command == "list":
            list_unresolved(database.conn)
        elif args.command == "show":
            show_attempt(database.conn, args.attempt_id)
        else:
            reconcile(database.conn, args)
    finally:
        database.close()


if __name__ == "__main__":
    main_cli()
