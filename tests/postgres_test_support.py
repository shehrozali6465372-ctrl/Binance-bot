"""Fail-closed connection guards shared by PostgreSQL integration tests."""

from __future__ import annotations


def validate_postgres_test_target(dsn: str, allowed_host: str) -> None:
    """Verify the actual test connection before any migration or database write.

    Local loopback databases remain supported for developer tests. Remote targets
    must match the explicit host allowlist, require TLS and SCRAM channel binding,
    and prove TLS is active on the client-to-database-proxy connection.
    """
    from psycopg import connect
    from psycopg.conninfo import conninfo_to_dict

    info = conninfo_to_dict(dsn)
    host = info.get("host", "")
    database = info.get("dbname") or info.get("database")
    hostaddr = info.get("hostaddr", "")
    local_host = host in {"localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if database != "binance_onchain_test" or not host or info.get("service"):
        raise RuntimeError("TEST_POSTGRES_DSN must target binance_onchain_test without a service alias")

    if local_host:
        if hostaddr and hostaddr not in {"127.0.0.1", "::1"}:
            raise RuntimeError("local PostgreSQL test target has a non-loopback hostaddr")
    else:
        if not allowed_host or host != allowed_host:
            raise RuntimeError("remote PostgreSQL test host does not match TEST_POSTGRES_ALLOWED_HOST allowlist")
        if info.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
            raise RuntimeError("remote PostgreSQL test target must require TLS")
        if info.get("channel_binding") != "require":
            raise RuntimeError("remote PostgreSQL test target must set channel_binding=require")
        if hostaddr:
            raise RuntimeError("remote PostgreSQL test target must not override DNS with hostaddr")

    conn = connect(
        dsn,
        connect_timeout=15,
        options="-c default_transaction_read_only=on",
        application_name="binance_postgres_test_target_guard",
    )
    try:
        connected_database = conn.execute("SELECT current_database()").fetchone()[0]
        if connected_database != "binance_onchain_test":
            raise RuntimeError("connected database identity is not binance_onchain_test")
        if not local_host and conn.pgconn.ssl_in_use is not True:
            raise RuntimeError("remote PostgreSQL test connection did not negotiate client TLS")
    finally:
        conn.close()
