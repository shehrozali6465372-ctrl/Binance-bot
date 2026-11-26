"""PostgreSQL implementation of the Layer1 discovery/evidence store contract.

The store shares an application-owned psycopg connection. It never opens a
second connection, reads environment variables, applies migrations, or closes
the connection supplied by its owner.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from .foundation import (
    AnnouncementEvidence, AssetIdentity, AssetIdentityProof, Candidate,
    EligibilityDecision, MarketAnalysisResult, MarketObservation,
    RelevanceScore, TrendCluster, TrendSignal, utc_now,
)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _payload(row: Mapping[str, Any]) -> dict:
    value = row["payload_json"]
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("persisted Layer1 payload is not a JSON object")
    return value


def _market(payload: dict) -> MarketObservation:
    payload = dict(payload)
    payload["history"] = tuple(payload.get("history") or ())
    record = MarketObservation(**payload)
    record.validate()
    return record


def _announcement(payload: dict) -> AnnouncementEvidence:
    payload = dict(payload)
    payload["asset_ids"] = tuple(payload.get("asset_ids") or ())
    record = AnnouncementEvidence(**payload)
    record.validate()
    return record


def _trend(payload: dict) -> TrendSignal:
    payload = dict(payload)
    payload["asset_ids"] = tuple(payload.get("asset_ids") or ())
    record = TrendSignal(**payload)
    record.validate()
    return record


class PostgresLayer1Store:
    """PostgreSQL-backed implementation of the Layer1Store persistence API."""

    def __init__(self, connection: Any):
        if connection is None or not callable(getattr(connection, "execute", None)):
            raise ValueError("an existing application-owned PostgreSQL connection is required")
        self.conn = connection

    def get_identity_proof(self, identity: AssetIdentity, now: Optional[str] = None) -> Optional[AssetIdentityProof]:
        row = self.conn.execute(
            "SELECT expires_at,payload_json FROM layer1_identity_proofs "
            "WHERE asset_id=%s AND base_asset=%s AND quote_asset=%s AND exchange_id='binance'",
            (identity.asset_id, identity.base_asset, identity.quote_asset),
        ).fetchone()
        if row is None:
            return None
        try:
            expires = row["expires_at"] if isinstance(row, Mapping) else row[0]
            payload = row["payload_json"] if isinstance(row, Mapping) else row[1]
            if isinstance(expires, str):
                expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            current = datetime.fromisoformat((now or utc_now()).replace("Z", "+00:00"))
            if expires <= current:
                raise ValueError("identity proof cache expired")
            if isinstance(payload, str):
                payload = json.loads(payload)
            proof = AssetIdentityProof(**payload)
            proof.validate()
            return proof
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            with self.conn.transaction():
                self.conn.execute(
                    "DELETE FROM layer1_identity_proofs WHERE asset_id=%s AND base_asset=%s "
                    "AND quote_asset=%s AND exchange_id='binance'",
                    (identity.asset_id, identity.base_asset, identity.quote_asset),
                )
            return None

    def save_identity_proof(self, proof: AssetIdentityProof, ttl_seconds: int) -> None:
        proof.validate()
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise ValueError("identity proof cache TTL must be a positive integer")
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO layer1_identity_proofs "
                "(asset_id,base_asset,quote_asset,exchange_id,status,expires_at,payload_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) "
                "ON CONFLICT(asset_id,base_asset,quote_asset,exchange_id) DO UPDATE SET "
                "status=EXCLUDED.status,expires_at=EXCLUDED.expires_at,payload_json=EXCLUDED.payload_json",
                (proof.asset_id, proof.base_asset, proof.quote_asset, proof.exchange_id,
                 proof.status, expires, _json(proof.__dict__)),
            )

    def save_market(self, observation: MarketObservation) -> None:
        observation.validate()
        key = hashlib.sha256(
            f"{observation.asset_id}|{observation.provider}|{observation.endpoint}|{observation.observed_at}".encode()
        ).hexdigest()
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO layer1_market_observations "
                "(observation_key,asset_id,provider,endpoint,observed_at,payload_json) "
                "VALUES (%s,%s,%s,%s,%s,%s::jsonb) "
                "ON CONFLICT(observation_key) DO UPDATE SET payload_json=EXCLUDED.payload_json",
                (key, observation.asset_id, observation.provider, observation.endpoint,
                 observation.observed_at, _json(observation.__dict__)),
            )

    def get_market_history(self, asset_id: str, provider: Optional[str] = None,
                           currency: Optional[str] = None) -> list[MarketObservation]:
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("market history requires a canonical asset ID")
        if provider is None:
            rows = self.conn.execute(
                "SELECT payload_json FROM layer1_market_observations WHERE asset_id=%s "
                "ORDER BY observed_at ASC,provider ASC", (asset_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT payload_json FROM layer1_market_observations WHERE asset_id=%s AND provider=%s "
                "ORDER BY observed_at ASC,provider ASC", (asset_id, provider),
            ).fetchall()
        records = [_market(_payload(row)) for row in rows]
        return [item for item in records if currency is None or item.currency == currency]

    def iter_announcement_revisions(self) -> tuple[AnnouncementEvidence, ...]:
        rows = self.conn.execute(
            "SELECT payload_json FROM layer1_announcement_revisions "
            "ORDER BY source_id,first_seen_at,revision_key"
        ).fetchall()
        return tuple(_announcement(_payload(row)) for row in rows)

    def iter_market_observations(self) -> tuple[MarketObservation, ...]:
        rows = self.conn.execute(
            "SELECT payload_json FROM layer1_market_observations "
            "ORDER BY observed_at,provider,observation_key"
        ).fetchall()
        return tuple(_market(_payload(row)) for row in rows)

    def iter_trend_signals(self) -> tuple[TrendSignal, ...]:
        rows = self.conn.execute(
            "SELECT payload_json FROM layer1_trend_signals ORDER BY observed_at,signal_key"
        ).fetchall()
        return tuple(_trend(_payload(row)) for row in rows)

    def save_market_analysis(self, result: MarketAnalysisResult) -> None:
        result.validate()
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO layer1_market_analyses "
                "(analysis_id,asset_id,provider,currency,observed_at,status,payload_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) "
                "ON CONFLICT(analysis_id) DO UPDATE SET status=EXCLUDED.status,payload_json=EXCLUDED.payload_json",
                (result.analysis_id,result.asset_id,result.provider,result.currency,
                 result.observed_at,result.status,_json(result.__dict__)),
            )

    def save_announcement(self, evidence: AnnouncementEvidence) -> None:
        evidence.validate()
        payload = _json(evidence.__dict__)
        revision_key = evidence.content_hash or hashlib.sha256(payload.encode()).hexdigest()
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO layer1_announcement_revisions(source_id,revision_key,first_seen_at,payload_json) "
                "VALUES (%s,%s,%s,%s::jsonb) ON CONFLICT(source_id,revision_key) DO NOTHING",
                (evidence.source_id,revision_key,utc_now(),payload),
            )
            self.conn.execute(
                "INSERT INTO layer1_announcement_evidence "
                "(source_id,source_url,publisher,event_type,published_at,observed_at,payload_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) "
                "ON CONFLICT(source_id) DO UPDATE SET source_url=EXCLUDED.source_url,"
                "publisher=EXCLUDED.publisher,event_type=EXCLUDED.event_type,"
                "published_at=EXCLUDED.published_at,observed_at=EXCLUDED.observed_at,"
                "payload_json=EXCLUDED.payload_json",
                (evidence.source_id,evidence.source_url,evidence.publisher,evidence.event_type,
                 evidence.published_at,evidence.observed_at,payload),
            )

    def save_trend(self, signal: TrendSignal) -> None:
        signal.validate()
        key = hashlib.sha256(
            f"{signal.source}|{signal.source_item_id}|{signal.topic}|{signal.content_hash}|{signal.observed_at}".encode()
        ).hexdigest()
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO layer1_trend_signals(signal_key,topic,source,observed_at,payload_json) "
                "VALUES (%s,%s,%s,%s,%s::jsonb) "
                "ON CONFLICT(signal_key) DO UPDATE SET payload_json=EXCLUDED.payload_json",
                (key,signal.topic,signal.source,signal.observed_at,_json(signal.__dict__)),
            )

    def save_trend_cluster(self, cluster: TrendCluster) -> None:
        cluster.validate()
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO layer1_trend_clusters "
                "(cluster_id,topic_key,asset_ids_json,source_count,independent_source_count,"
                "signal_count,observed_at,source_refs_json,confidence_limit,created_at) "
                "VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s,%s) "
                "ON CONFLICT(cluster_id) DO UPDATE SET topic_key=EXCLUDED.topic_key,"
                "asset_ids_json=EXCLUDED.asset_ids_json,source_count=EXCLUDED.source_count,"
                "independent_source_count=EXCLUDED.independent_source_count,signal_count=EXCLUDED.signal_count,"
                "observed_at=EXCLUDED.observed_at,source_refs_json=EXCLUDED.source_refs_json,"
                "confidence_limit=EXCLUDED.confidence_limit,created_at=EXCLUDED.created_at",
                (cluster.cluster_id,cluster.topic_key,_json(list(cluster.asset_ids)),cluster.source_count,
                 cluster.independent_source_count,cluster.signal_count,cluster.observed_at,
                 _json(list(cluster.source_refs)),cluster.confidence_limit,utc_now()),
            )

    def save_candidate(self, candidate: Candidate) -> None:
        evidence = {
            "events": list(candidate.event_ids), "event_clusters": list(candidate.event_cluster_ids),
            "markets": list(candidate.market_observation_ids), "trends": list(candidate.trend_signal_ids),
            "trend_clusters": list(candidate.trend_cluster_ids),
            "onchain_transfer_summaries": list(candidate.onchain_transfer_summary_ids),
            "eligibility": candidate.eligibility.__dict__,
        }
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO layer1_candidates "
                "(candidate_id,asset_id,state,rejection_reasons_json,evidence_refs_json,updated_at) "
                "VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s) "
                "ON CONFLICT(candidate_id) DO UPDATE SET asset_id=EXCLUDED.asset_id,state=EXCLUDED.state,"
                "rejection_reasons_json=EXCLUDED.rejection_reasons_json,"
                "evidence_refs_json=EXCLUDED.evidence_refs_json,updated_at=EXCLUDED.updated_at",
                (candidate.candidate_id,candidate.asset_id,candidate.state,
                 _json(list(candidate.rejection_reasons)),_json(evidence),utc_now()),
            )

    def save_rejection(self, symbol: str, reason_code: str, source: str,
                       source_observed_at: Optional[str] = None,
                       details: Optional[Mapping[str, Any]] = None) -> None:
        if not all(isinstance(value,str) and value.strip() for value in (symbol,reason_code,source)):
            raise ValueError("candidate rejection symbol/reason/source must be non-empty")
        payload = _json(dict(details or {}))
        fingerprint = _json({
            "symbol":symbol.upper(),"reason_code":reason_code,"source":source,
            "source_observed_at":source_observed_at,"details":json.loads(payload),
        })
        rejection_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO layer1_candidate_rejections "
                "(rejection_id,symbol,reason_code,source,source_observed_at,recorded_at,details_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(rejection_id) DO NOTHING",
                (rejection_id,symbol.upper(),reason_code,source,source_observed_at,utc_now(),payload),
            )

    def save_score(self, score: RelevanceScore) -> None:
        if (not isinstance(score, RelevanceScore) or isinstance(score.score,bool)
                or not isinstance(score.score,(int,float)) or not 0 <= score.score <= 100):
            raise ValueError("candidate score must be a valid finite score")
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO layer1_candidate_scores "
                "(candidate_id,score_version,score,components_json,reason,created_at) "
                "VALUES (%s,%s,%s,%s::jsonb,%s,%s) "
                "ON CONFLICT(candidate_id,score_version) DO UPDATE SET score=EXCLUDED.score,"
                "components_json=EXCLUDED.components_json,reason=EXCLUDED.reason,created_at=EXCLUDED.created_at",
                (score.candidate_id,score.score_version,score.score,_json(dict(score.components)),
                 score.reason,utc_now()),
            )

    def close(self) -> None:
        """Compatibility no-op: the PostgreSQL connection is owned by the application."""
        return None
