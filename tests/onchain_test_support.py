"""Narrow worker-test dependency for supplying already validated mapping configuration."""
from __future__ import annotations


class MappingStoreStub:
    """Worker tests exercise ingestion, not anchor-observation persistence."""

    def __init__(self, engine, *mappings):
        self.engine = engine
        self._mappings = tuple(mappings)

    def list_verified_mappings(self, network_id=None):
        return [
            mapping for mapping in self._mappings
            if network_id is None or mapping.network_id == network_id
        ]

    def get_latest_accepted_observation(self, mapping_id):
        return None

    def get_observation(self, observation_id):
        return None

    def close(self):
        return None


def seed_accepted_observation_page(ingestion_store, mapping_store, eligibility, mapping, observation):
    """Create a distinct signed provider-observation page; never reuse a transfer event."""
    from dataclasses import asdict
    from layer1.onchain import OnChainObservationProvenance
    from layer1.onchain_providers import (
        ProviderResponseReceipt, _ACTIVE_PAGE_RECEIPTS,
        _approved_endpoint_profile_sha256, _capture_provider_run_receipts,
        drain_provider_run_receipts,
    )

    network = observation.network_id
    provider = observation.provider
    scope = observation.scope
    if network == "bitcoin-mainnet":
        cursor = {
            "observed_tip_height": observation.block_height + 5,
            "minimum_confirmations": 6,
        }
        blocks, slots = ({
            "network_id": network, "provider": provider, "scope": scope,
            "block_number": observation.block_height,
            "block_hash": observation.block_hash, "block_time": observation.block_time,
        },), ()
    elif network in {"ethereum-mainnet", "bnb-smart-chain-mainnet"}:
        cursor = {
            "finalized_height": observation.block_height,
            "finality_reference": observation.finality_reference,
        }
        blocks, slots = ({
            "network_id": network, "provider": provider, "scope": scope,
            "block_number": observation.block_height,
            "block_hash": observation.block_hash, "block_time": observation.block_time,
        },), ()
    elif network == "solana-mainnet":
        cursor = {"finalized_slot": observation.block_height}
        blocks = ()
        slots = ({
            "network_id": network, "provider": provider, "scope": scope,
            "slot": observation.block_height, "produced": True,
            "block_hash": observation.block_hash, "block_time": observation.block_time,
        },)
    elif network == "xrpl-mainnet":
        cursor = {
            "validated_head_height": observation.block_height,
            "finality_reference": observation.finality_reference,
        }
        blocks, slots = ({
            "network_id": network, "provider": provider, "scope": scope,
            "block_number": observation.block_height,
            "block_hash": observation.block_hash, "block_time": observation.block_time,
        },), ()
    else:
        raise ValueError("unsupported test observation network")

    receipt = ProviderResponseReceipt(
        sequence=1, provider=provider, network_id=network,
        method="get_anchor_observation", request_sha256="a" * 64,
        response_sha256="b" * 64, response_bytes=128, http_status=200,
        received_at=observation.observed_at,
        endpoint_profile_sha256=_approved_endpoint_profile_sha256(provider, network),
    )

    @_capture_provider_run_receipts
    def captured():
        _ACTIVE_PAGE_RECEIPTS.get().append(receipt)
        return drain_provider_run_receipts()

    cursor_key = "anchor-observation:" + mapping.mapping_id
    ingestion_store.commit_page(
        cursor_key, cursor, (), expected_cursor=None,
        scope_identity=(network, provider, scope),
        canonical_blocks=blocks, canonical_slots=slots,
        provider_receipts=captured(),
        provider_observations=(asdict(observation),),
    )
    page_id = next(
        page_id for key, page_id in ingestion_store.list_ingestion_pages()
        if key == cursor_key
    )
    mapping_store.engine.sign_ingestion_page(ingestion_store, cursor_key, page_id)
    provenance = OnChainObservationProvenance(
        cursor_key, page_id, observation.observation_id,
    )
    mapping_store.save_verified(
        eligibility, mapping, observation,
        ingestion_store=ingestion_store, provenance=provenance,
    )
    return provenance
