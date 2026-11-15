"""PostgreSQL adapter for the legacy post-history and analytics database contract."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class PostgresLegacyDatabase:
    """Implements Database's public history/run/metrics API using PostgreSQL.

    No SQLite database is opened in PostgreSQL mode. The conn attribute remains
    None so SQLite-only code paths cannot accidentally issue local persistence.
    """

    def __init__(self, publication_store: Any):
        connection = getattr(publication_store, "conn", None)
        if connection is None or not callable(getattr(connection, "execute", None)):
            raise TypeError("PostgreSQL publication store is required")
        self.store = publication_store
        self.pg_conn = connection
        self.conn = None

    def close(self) -> None:
        # The PostgreSQL connection is owned by PostgresPublicationStore.
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    @staticmethod
    def _metadata(row: Any) -> dict:
        value = row["metadata"]
        if value is None:
            return {}
        if isinstance(value, str):
            value = json.loads(value)
        return value if isinstance(value, dict) else {}

    def save_post(self, post: Any) -> int:
        if isinstance(post, dict):
            content = post.get("content") or post.get("text") or ""
            metadata = {key: value for key, value in post.items() if key not in {"content", "text"}}
            coin_symbol = metadata.get("coin_symbol") or metadata.get("symbol")
        else:
            content = str(post)
            metadata = {}
            coin_symbol = None
        with self.pg_conn.transaction():
            row = self.pg_conn.execute(
                "INSERT INTO posts(coin_symbol,content,metadata) VALUES (%s,%s,%s::jsonb) RETURNING id",
                (coin_symbol,content,json.dumps(metadata,default=str,sort_keys=True,separators=(",",":"))),
            ).fetchone()
        return int(row["id"])

    def save_metrics(self, views: int, traders: int, post_id: Optional[int] = None) -> None:
        with self.pg_conn.transaction():
            self.pg_conn.execute(
                "INSERT INTO metrics(post_id,views,traders) VALUES (%s,%s,%s)",
                (post_id,int(views),int(traders)),
            )

    def recent_posts(self, limit: int = 100) -> List[Dict[str, Any]]:
        if isinstance(limit,bool) or not isinstance(limit,int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        rows=self.pg_conn.execute(
            "SELECT created_at,coin_symbol,content,metadata FROM posts ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        return [{
            "created_at": row["created_at"].isoformat(),
            "coin_symbol": row["coin_symbol"],
            "content": row["content"],
            "metadata": self._metadata(row),
        } for row in rows]

    def get_posted_symbols(self, hours: int = 48) -> set:
        rows=self.pg_conn.execute(
            "SELECT coin_symbol FROM posts WHERE coin_symbol IS NOT NULL ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return {str(row["coin_symbol"]).upper() for row in rows if row["coin_symbol"]}

    def get_post_count_for_symbol(self, symbol: str, hours: int = 48) -> int:
        row=self.pg_conn.execute(
            "SELECT COUNT(*) AS cnt FROM posts WHERE coin_symbol=%s",(symbol.upper(),)
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def get_posted_hours_dict(self, hours: int = 72) -> Dict[str,float]:
        now=datetime.now(timezone.utc)
        rows=self.pg_conn.execute(
            "SELECT coin_symbol,created_at FROM posts WHERE created_at IS NOT NULL ORDER BY id DESC LIMIT 200"
        ).fetchall()
        result={}
        for row in rows:
            symbol=row["coin_symbol"]
            if not symbol:
                continue
            posted=row["created_at"]
            if isinstance(posted,str):
                try:
                    posted=datetime.fromisoformat(posted.replace("Z","+00:00"))
                except ValueError:
                    continue
            if posted.tzinfo is None:
                posted=posted.replace(tzinfo=timezone.utc)
            delta=(now-posted.astimezone(timezone.utc)).total_seconds()/3600.0
            key=symbol.upper()
            if key not in result or delta < result[key]:
                result[key]=delta
        return result

    def get_today_post_count(self) -> int:
        today_start=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
        row=self.pg_conn.execute(
            "SELECT COUNT(*) AS cnt FROM post_analytics WHERE created_at >= %s",
            (today_start,),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def save_run(self, status: str, summary: Dict[str,Any]) -> None:
        with self.pg_conn.transaction():
            self.pg_conn.execute(
                "INSERT INTO runs(status,summary) VALUES (%s,%s::jsonb)",
                (status,json.dumps(summary,default=str,sort_keys=True,separators=(",",":"))),
            )

    def get_top_performers(self, limit: int = 2) -> List[str]:
        if isinstance(limit,bool) or not isinstance(limit,int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        rows=self.pg_conn.execute(
            "SELECT coin_symbol,AVG(views) AS avg_views FROM post_analytics "
            "WHERE views IS NOT NULL GROUP BY coin_symbol ORDER BY avg_views DESC LIMIT %s",
            (limit,),
        ).fetchall()
        return [row["coin_symbol"] for row in rows if row["coin_symbol"]]
