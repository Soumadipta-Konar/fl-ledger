"""Unit tests for EIP-712 client root signing and domain separation."""

from eth_account import Account
from ledger.sign import (
    sign_client_root,
    recover_client_signer,
    verify_client_signature,
)


def test_sign_and_recover_valid() -> None:
    client_acct = Account.create()
    session = b"\x01" * 32
    round_num = 1
    root = b"\xaa" * 32
    nonce = 0
    chain_id = 31337
    contract_address = "0x" + "1" * 40

    sig = sign_client_root(
        private_key=client_acct.key,
        session=session,
        round_num=round_num,
        client=client_acct.address,
        root=root,
        nonce=nonce,
        chain_id=chain_id,
        verifying_contract=contract_address,
    )

    recovered = recover_client_signer(
        signature=sig,
        session=session,
        round_num=round_num,
        client=client_acct.address,
        root=root,
        nonce=nonce,
        chain_id=chain_id,
        verifying_contract=contract_address,
    )
    assert recovered.lower() == client_acct.address.lower()

    assert verify_client_signature(
        signature=sig,
        session=session,
        round_num=round_num,
        expected_client=client_acct.address,
        root=root,
        nonce=nonce,
        chain_id=chain_id,
        verifying_contract=contract_address,
    )


def test_replay_across_chain_id_rejected() -> None:
    client_acct = Account.create()
    session = b"\x01" * 32
    round_num = 1
    root = b"\xaa" * 32
    contract = "0x" + "1" * 40

    # Signed for chain 31337
    sig = sign_client_root(
        private_key=client_acct.key,
        session=session,
        round_num=round_num,
        client=client_acct.address,
        root=root,
        nonce=0,
        chain_id=31337,
        verifying_contract=contract,
    )

    # Replay on chain 1 must fail
    assert not verify_client_signature(
        signature=sig,
        session=session,
        round_num=round_num,
        expected_client=client_acct.address,
        root=root,
        nonce=0,
        chain_id=1,
        verifying_contract=contract,
    )


def test_replay_across_contract_address_rejected() -> None:
    client_acct = Account.create()
    session = b"\x01" * 32
    round_num = 1
    root = b"\xaa" * 32

    sig = sign_client_root(
        private_key=client_acct.key,
        session=session,
        round_num=round_num,
        client=client_acct.address,
        root=root,
        nonce=0,
        chain_id=31337,
        verifying_contract="0x" + "1" * 40,
    )

    # Replay on different contract address must fail
    assert not verify_client_signature(
        signature=sig,
        session=session,
        round_num=round_num,
        expected_client=client_acct.address,
        root=root,
        nonce=0,
        chain_id=31337,
        verifying_contract="0x" + "2" * 40,
    )


def test_replay_across_session_or_round_rejected() -> None:
    client_acct = Account.create()
    contract = "0x" + "1" * 40

    sig = sign_client_root(
        private_key=client_acct.key,
        session=b"\x01" * 32,
        round_num=1,
        client=client_acct.address,
        root=b"\xaa" * 32,
        nonce=0,
        chain_id=31337,
        verifying_contract=contract,
    )

    # Different round
    assert not verify_client_signature(
        signature=sig,
        session=b"\x01" * 32,
        round_num=2,
        expected_client=client_acct.address,
        root=b"\xaa" * 32,
        nonce=0,
        chain_id=31337,
        verifying_contract=contract,
    )

    # Different session
    assert not verify_client_signature(
        signature=sig,
        session=b"\x02" * 32,
        round_num=1,
        expected_client=client_acct.address,
        root=b"\xaa" * 32,
        nonce=0,
        chain_id=31337,
        verifying_contract=contract,
    )
