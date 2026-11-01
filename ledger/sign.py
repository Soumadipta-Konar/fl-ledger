"""EIP-712 structured data signing and verification for fl-ledger.

Invariants:
- Domain separator incorporates chainId and verifyingContract address to prevent cross-chain/cross-contract replay.
- Signed struct: ClientRoot(bytes32 session, uint256 round, address client, bytes32 root, uint256 nonce).
- Nonce and round binding prevent intra-session replay attacks.
"""

from __future__ import annotations

from typing import Any
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import to_checksum_address


def build_eip712_dict(
    session: bytes,
    round_num: int,
    client: str,
    root: bytes,
    nonce: int,
    chain_id: int,
    verifying_contract: str,
) -> dict[str, Any]:
    """Construct EIP-712 structured data dictionary for ClientRoot."""
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "ClientRoot": [
                {"name": "session", "type": "bytes32"},
                {"name": "round", "type": "uint256"},
                {"name": "client", "type": "address"},
                {"name": "root", "type": "bytes32"},
                {"name": "nonce", "type": "uint256"},
            ],
        },
        "primaryType": "ClientRoot",
        "domain": {
            "name": "FL-Ledger",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": to_checksum_address(verifying_contract),
        },
        "message": {
            "session": session,
            "round": round_num,
            "client": to_checksum_address(client),
            "root": root,
            "nonce": nonce,
        },
    }


def sign_client_root(
    private_key: str | bytes,
    session: bytes,
    round_num: int,
    client: str,
    root: bytes,
    nonce: int,
    chain_id: int,
    verifying_contract: str,
) -> bytes:
    """Sign an EIP-712 ClientRoot payload, returning a 65-byte signature (r, s, v)."""
    typed_data = build_eip712_dict(
        session=session,
        round_num=round_num,
        client=client,
        root=root,
        nonce=nonce,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
    )
    signable_message = encode_typed_data(full_message=typed_data)
    signed = Account.sign_message(signable_message, private_key=private_key)
    return bytes(signed.signature)


def recover_client_signer(
    signature: bytes,
    session: bytes,
    round_num: int,
    client: str,
    root: bytes,
    nonce: int,
    chain_id: int,
    verifying_contract: str,
) -> str:
    """Recover the Ethereum checksum address that generated the ClientRoot signature."""
    typed_data = build_eip712_dict(
        session=session,
        round_num=round_num,
        client=client,
        root=root,
        nonce=nonce,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
    )
    signable_message = encode_typed_data(full_message=typed_data)
    recovered_address = Account.recover_message(signable_message, signature=signature)
    return to_checksum_address(recovered_address)


def verify_client_signature(
    signature: bytes,
    session: bytes,
    round_num: int,
    expected_client: str,
    root: bytes,
    nonce: int,
    chain_id: int,
    verifying_contract: str,
) -> bool:
    """Verify that signature was signed by expected_client for this session, round, and root."""
    try:
        recovered = recover_client_signer(
            signature=signature,
            session=session,
            round_num=round_num,
            client=expected_client,
            root=root,
            nonce=nonce,
            chain_id=chain_id,
            verifying_contract=verifying_contract,
        )
        return recovered == to_checksum_address(expected_client)
    except Exception:
        return False
