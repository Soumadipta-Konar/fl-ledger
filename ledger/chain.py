"""Web3 wrapper for interacting with local Session contract deployments.

Reads configuration from .env or keyword arguments. No hardcoded addresses, keys, or URLs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3
from web3.types import TxReceipt

load_dotenv()

DEFAULT_RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
DEFAULT_CHAIN_ID = int(os.getenv("CHAIN_ID", "31337"))


def get_web3(rpc_url: str = DEFAULT_RPC_URL) -> Web3:
    """Return configured Web3 instance."""
    return Web3(Web3.HTTPProvider(rpc_url))


def load_session_abi_and_bytecode(
    artifact_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Load Session ABI and bytecode from Foundry compiled output."""
    if artifact_path is None:
        artifact_path = (
            Path(__file__).parent.parent
            / "out"
            / "Session.sol"
            / "Session.json"
        )
    with open(artifact_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["abi"], data["bytecode"]["object"]


def deploy_session(
    w3: Web3,
    deployer_key: str,
    params: Mapping[str, Any],
) -> tuple[str, TxReceipt]:
    """Deploy Session contract with SessionParams struct."""
    abi, bytecode = load_session_abi_and_bytecode()
    account = Account.from_key(deployer_key)
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    tuple_params = (
        params["initialAdmin"],
        params["adminDelay"],
        params["server"],
        params["treasury"],
        params["maxClients"],
        params["blockSize"],
        params["scaleBits"],
        params["challengeWindowBlocks"],
        params["withdrawalDelayBlocks"],
        params["bondAmountWei"],
        params["challengerDepositWei"],
        params["rewardShareBps"],
        params["generatorsHash"],
    )

    construct_txn = contract.constructor(tuple_params).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 6_000_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": DEFAULT_CHAIN_ID,
    })

    signed = account.sign_transaction(construct_txn)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1 or receipt.contractAddress is None:
        raise RuntimeError(f"deployment failed; status={receipt.status}, contractAddress={receipt.contractAddress}")

    return receipt.contractAddress, receipt


def send_contract_tx(
    w3: Web3,
    contract_address: str,
    private_key: str,
    func_name: str,
    *args: Any,
    value: int = 0,
    gas_limit: int = 500_000,
) -> TxReceipt:
    """Build, sign, send, and wait for contract transaction receipt."""
    abi, _ = load_session_abi_and_bytecode()
    contract = w3.eth.contract(address=contract_address, abi=abi)
    account = Account.from_key(private_key)
    fn = getattr(contract.functions, func_name)(*args)

    tx_data = fn.build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "value": value,
        "gas": gas_limit,
        "gasPrice": w3.eth.gas_price,
        "chainId": DEFAULT_CHAIN_ID,
    })

    signed = account.sign_transaction(tx_data)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash)


def advance_blocks(w3: Web3, num_blocks: int) -> None:
    """Advance local Anvil node by num_blocks using anvil_mine RPC."""
    w3.provider.make_request("anvil_mine", [hex(num_blocks)])  # type: ignore[union-attr]
