"""Verifiable hash-to-curve generator derivation for BN254 G1 in fl-ledger.

Derives:
- Blinding generator H
- Block element generators G_0 .. G_{m-1} (m = 32)
Output:
- params/generators.json containing affine coordinates and the committed keccak256 hash.
"""

from __future__ import annotations

import json
from pathlib import Path
from eth_utils import keccak
from py_ecc.bn128 import is_on_curve, b, field_modulus, FQ

NUM_GENERATORS: int = 32
B_COEFF: int = int(b)
Q: int = field_modulus


def hash_to_g1(label: str) -> tuple[int, int]:
    """Deterministically find a point on y^2 = x^3 + 3 (mod q) using try-and-increment."""
    counter = 0
    while True:
        seed = f"{label}:{counter}".encode("utf-8")
        x = int.from_bytes(keccak(seed), "big") % Q
        z = (pow(x, 3, Q) + B_COEFF) % Q
        if pow(z, (Q - 1) // 2, Q) == 1:
            y = pow(z, (Q + 1) // 4, Q)
            if y > Q // 2:
                y = Q - y
            if is_on_curve((FQ(x), FQ(y)), b):
                return x, y
        counter += 1


def main() -> None:
    h_x, h_y = hash_to_g1("fl-ledger:bn254:H")
    generators: list[dict[str, str]] = []
    raw_bytes = bytearray()

    # Prepend H
    raw_bytes.extend(h_x.to_bytes(32, "big"))
    raw_bytes.extend(h_y.to_bytes(32, "big"))

    for i in range(NUM_GENERATORS):
        gx, gy = hash_to_g1(f"fl-ledger:bn254:G:{i}")
        generators.append({"x": hex(gx), "y": hex(gy)})
        raw_bytes.extend(gx.to_bytes(32, "big"))
        raw_bytes.extend(gy.to_bytes(32, "big"))

    generators_hash = "0x" + keccak(bytes(raw_bytes)).hex()

    output_data = {
        "curve": "BN254_G1",
        "num_generators": NUM_GENERATORS,
        "generators_hash": generators_hash,
        "H": {"x": hex(h_x), "y": hex(h_y)},
        "G": generators,
    }

    out_file = Path(__file__).parent / "generators.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"Generated {NUM_GENERATORS} generators + H -> {out_file}")
    print(f"Committed hash: {generators_hash}")


if __name__ == "__main__":
    main()
