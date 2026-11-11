import unittest
from datetime import datetime, timezone

from layer1.onchain_ingestion import normalize_solana_token_transfer_instructions
from layer1.onchain_providers import SolanaAddressTransaction, ProviderTransportError

MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOURCE = "So11111111111111111111111111111111111111112"
DESTINATION = "11111111111111111111111111111111"
WALLET = "Vote111111111111111111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
BLOCKHASH = "11111111111111111111111111111111"
SIGNATURE = "3jUKrQp1UGq5ih6FTDUUt2kkqUfoG2o4kY5T1DoVHK2tXXDLdxJSXzuJGY4JPoRivgbi45U2bc7LZfMa6C4R3szX"
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def b58encode(raw):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, rem = divmod(number, 58)
        encoded = alphabet[rem] + encoded
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + (encoded or "")


DEST_OWNER = b58encode(bytes([2]) * 32)


def rpc_tx(*, opcode=12, amount=1234567, decimals=6, program=TOKEN_PROGRAM,
           slot=300, owner=WALLET, signature=SIGNATURE, instruction_index=0,
           inner=None, loaded=None, err=None, mint=MINT, account_mint=MINT):
    keys = [SOURCE, MINT, DESTINATION, WALLET, program, "11111111111111111111111111111111"]
    data = bytes([opcode]) + amount.to_bytes(8, "little")
    accounts = [0, 1, 2, 3] if opcode == 12 else [0, 2, 3]
    if opcode == 12:
        data += bytes([decimals])
    ix = {"programIdIndex": 4, "accounts": accounts, "data": b58encode(data)}
    instructions = [ix]
    if inner is not None:
        instructions = [{"programIdIndex": 5, "accounts": [], "data": b58encode(b"\x00")}]
    meta = {
        "err": err,
        "loadedAddresses": loaded or {"writable": [], "readonly": []},
        "innerInstructions": ([{"index": 0, "instructions": [inner]}] if inner else []),
        "preTokenBalances": [
            {"accountIndex": 0, "mint": account_mint, "owner": owner,
             "uiTokenAmount": {"decimals": decimals, "amount": str(amount)}},
            {"accountIndex": 2, "mint": mint, "owner": DEST_OWNER,
             "uiTokenAmount": {"decimals": decimals, "amount": str(amount)}},
        ],
        "postTokenBalances": [
            {"accountIndex": 0, "mint": account_mint, "owner": owner,
             "uiTokenAmount": {"decimals": decimals, "amount": "0"}},
            {"accountIndex": 2, "mint": mint, "owner": DEST_OWNER,
             "uiTokenAmount": {"decimals": decimals, "amount": str(amount)}},
        ],
    }
    if loaded:
        keys = [SOURCE, MINT, DESTINATION, WALLET, program, "11111111111111111111111111111111"]
    raw = {
        "signature": signature, "slot": slot, "transactionIndex": 17,
        "blockTime": 1794398400,
        "transaction": {"signatures": [signature], "message": {
            "accountKeys": keys, "instructions": instructions,
        }},
        "meta": meta,
    }
    return SolanaAddressTransaction(signature, slot, 1794398400, raw)


class SolanaTokenInstructionNormalizationTests(unittest.TestCase):
    def normalize(self, record, monitored=WALLET, mapped_mint=MINT, decimals=6):
        return normalize_solana_token_transfer_instructions(
            record, asset_id="coingecko:usd-coin", mapping_id="sol-usdc-v1",
            mint=mapped_mint, token_standard="SPL_TOKEN",
            decimals=decimals, monitored_address=monitored,
            canonical_block_hash=BLOCKHASH,
            canonical_block_time="2026-11-11T12:00:00+00:00",
            observed_at=NOW.isoformat(),
        )

    def test_transfer_checked_emits_exact_raw_amount_and_stable_outer_instruction_identity(self):
        record = rpc_tx()
        events = self.normalize(record)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.event_id, SIGNATURE + ":outer:0")
        self.assertEqual(event.transaction_hash, SIGNATURE)
        self.assertEqual(event.amount_raw, "1234567")
        self.assertEqual(event.decimals, 6)
        self.assertEqual(event.from_address, SOURCE)
        self.assertEqual(event.to_address, DESTINATION)
        self.assertEqual(event.block_number, 300)
        self.assertEqual(event.block_hash, BLOCKHASH)

    def test_transfer_instruction_uses_balance_metadata_to_prove_mint(self):
        record = rpc_tx(opcode=3)
        events = self.normalize(record)
        self.assertEqual(events[0].amount_raw, "1234567")

    def test_inner_cpi_transfer_has_distinct_trace_identity(self):
        inner = {"programIdIndex": 4, "accounts": [0, 1, 2, 3],
                 "data": b58encode(bytes([12]) + (55).to_bytes(8, "little") + bytes([6])),
                 "stackHeight": 2}
        events = self.normalize(rpc_tx(inner=inner))
        self.assertEqual(events[0].event_id, SIGNATURE + ":inner:0:0")

    def test_same_transaction_multiple_transfers_remain_distinct(self):
        record = rpc_tx()
        second = {"programIdIndex": 4, "accounts": [0, 1, 2, 3],
                  "data": b58encode(bytes([12]) + (99).to_bytes(8, "little") + bytes([6]))}
        record.raw["transaction"]["message"]["instructions"].append(second)
        events = self.normalize(record)
        self.assertEqual({event.event_id for event in events}, {
            SIGNATURE + ":outer:0", SIGNATURE + ":outer:1",
        })

    def test_versioned_loaded_program_address_is_resolved_in_canonical_account_order(self):
        record = rpc_tx()
        message = record.raw["transaction"]["message"]
        message["accountKeys"] = [SOURCE, MINT, DESTINATION, WALLET]
        message["addressTableLookups"] = [{"accountKey": "AddressLookupTable1111111111111111111111111",
                                           "writableIndexes": [0], "readonlyIndexes": []}]
        message["instructions"][0]["programIdIndex"] = 4
        record.raw["meta"]["loadedAddresses"] = {"writable": [TOKEN_PROGRAM], "readonly": []}
        events = self.normalize(record)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, SIGNATURE + ":outer:0")

    def test_v1_transaction_with_transaction_config_keeps_instruction_identity(self):
        record = rpc_tx()
        record.raw["version"] = 1
        record.raw["transaction"]["message"]["transactionConfig"] = {
            "computeUnitLimit": 200000, "priorityFeeLamports": 5000,
        }
        events = self.normalize(record)
        self.assertEqual(events[0].event_id, SIGNATURE + ":outer:0")
        self.assertEqual(events[0].amount_raw, "1234567")

    def test_versioned_transaction_requires_resolved_lookup_addresses(self):
        record = rpc_tx()
        message = record.raw["transaction"]["message"]
        message["addressTableLookups"] = [{
            "accountKey": "AddressLookupTable1111111111111111111111111",
            "writableIndexes": [0], "readonlyIndexes": [],
        }]
        record.raw["meta"].pop("loadedAddresses")
        with self.assertRaises(ProviderTransportError):
            self.normalize(record)

    def test_versioned_transaction_rejects_incomplete_lookup_address_resolution(self):
        record = rpc_tx()
        message = record.raw["transaction"]["message"]
        message["addressTableLookups"] = [{
            "accountKey": "AddressLookupTable1111111111111111111111111",
            "writableIndexes": [0], "readonlyIndexes": [],
        }]
        record.raw["meta"]["loadedAddresses"] = {"writable": [], "readonly": []}
        with self.assertRaises(ProviderTransportError):
            self.normalize(record)

    def test_transaction_signature_must_match_exact_history_signature(self):
        record = rpc_tx()
        record.raw["transaction"]["signatures"] = ["1" * 64]
        with self.assertRaises(ProviderTransportError):
            self.normalize(record)

    def test_rejects_failed_transaction(self):
        with self.assertRaises(ProviderTransportError):
            self.normalize(rpc_tx(err={"InstructionError": [0, "Custom"]}))

    def test_rejects_conflicting_source_and_destination_balance_mints(self):
        with self.assertRaises(ProviderTransportError):
            self.normalize(rpc_tx(mint="So11111111111111111111111111111111111111112"))

    def test_transfer_checked_for_an_unmapped_mint_is_ignored(self):
        record = rpc_tx(mint="So11111111111111111111111111111111111111112")
        record.raw["transaction"]["message"]["accountKeys"][1] = "So11111111111111111111111111111111111111112"
        self.assertEqual(self.normalize(record), ())

    def test_rejects_mismatched_transfer_checked_decimals(self):
        with self.assertRaises(ProviderTransportError):
            self.normalize(rpc_tx(decimals=9))

    def test_requires_monitored_wallet_to_be_proven_by_token_balance_owner(self):
        self.assertEqual(
            self.normalize(rpc_tx(owner=b58encode(bytes([3]) * 32)),
                           monitored=WALLET),
            (),
        )

    def test_token_2022_is_rejected_until_extension_aware_instruction_decoding_exists(self):
        with self.assertRaises(ValueError):
            normalize_solana_token_transfer_instructions(
                rpc_tx(program=TOKEN_2022), asset_id="coingecko:usd-coin",
                mapping_id="sol-usdc-2022", mint=MINT, token_standard="TOKEN_2022",
                decimals=6, monitored_address=WALLET,
                canonical_block_hash=BLOCKHASH,
                canonical_block_time="2026-11-11T12:00:00+00:00",
                observed_at=NOW.isoformat())

    def test_rejects_malformed_inner_instruction_trace_without_fabricating_indexes(self):
        record = rpc_tx(inner={
            "programIdIndex": 99, "accounts": [0, 1, 2, 3],
            "data": b58encode(bytes([12]) + (55).to_bytes(8, "little") + bytes([6])),
        })
        with self.assertRaises(ProviderTransportError):
            self.normalize(record)

    def test_rejects_missing_canonical_slot_evidence(self):
        record = rpc_tx()
        record.raw["slot"] = 0
        with self.assertRaises(ProviderTransportError):
            self.normalize(record)


if __name__ == "__main__":
    unittest.main()
