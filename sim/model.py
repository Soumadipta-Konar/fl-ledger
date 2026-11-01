"""Small neural network and dataset utilities for federated learning simulation.

Uses digits classification (8x8 pixels = 64 features, 10 classes) with an MLP.
"""

from __future__ import annotations

from typing import Tuple
import numpy as np
from sklearn.datasets import load_digits


class SmallMLP:
    """Two-layer Multi-Layer Perceptron (64 -> 16 -> 10)."""

    def __init__(self, seed: int = 42) -> None:
        rng = np.random.default_rng(seed)
        # 64 -> 16
        self.w1 = rng.normal(0, 0.1, (64, 16)).astype(np.float64)
        self.b1 = np.zeros(16, dtype=np.float64)
        # 16 -> 10
        self.w2 = rng.normal(0, 0.1, (16, 10)).astype(np.float64)
        self.b2 = np.zeros(10, dtype=np.float64)

    def get_flat_weights(self) -> np.ndarray:
        """Flatten all parameters into a 1D vector."""
        return np.concatenate([
            self.w1.ravel(),
            self.b1.ravel(),
            self.w2.ravel(),
            self.b2.ravel(),
        ])

    def set_flat_weights(self, flat: np.ndarray) -> None:
        """Restore parameters from a 1D vector."""
        idx = 0
        w1_size = 64 * 16
        self.w1 = flat[idx : idx + w1_size].reshape((64, 16))
        idx += w1_size

        b1_size = 16
        self.b1 = flat[idx : idx + b1_size].reshape(16)
        idx += b1_size

        w2_size = 16 * 10
        self.w2 = flat[idx : idx + w2_size].reshape((16, 10))
        idx += w2_size

        b2_size = 10
        self.b2 = flat[idx : idx + b2_size].reshape(10)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Compute softmax probabilities."""
        h = np.maximum(0, x @ self.w1 + self.b1)  # ReLU
        logits = h @ self.w2 + self.b2
        exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        return exp_logits / np.sum(exp_logits, axis=1, keepdims=True)

    def train_step(self, x: np.ndarray, y: np.ndarray, lr: float = 0.05) -> None:
        """Perform one batch gradient descent step."""
        n = x.shape[0]
        h = np.maximum(0, x @ self.w1 + self.b1)
        probs = self.forward(x)

        # One-hot encode targets
        one_hot = np.zeros_like(probs)
        one_hot[np.arange(n), y] = 1.0

        d_logits = (probs - one_hot) / n
        dw2 = h.T @ d_logits
        db2 = np.sum(d_logits, axis=0)

        dh = d_logits @ self.w2.T
        dh[h <= 0] = 0.0
        dw1 = x.T @ dh
        db1 = np.sum(dh, axis=0)

        self.w1 -= lr * dw1
        self.b1 -= lr * db1
        self.w2 -= lr * dw2
        self.b2 -= lr * db2

    def evaluate(self, x: np.ndarray, y: np.ndarray) -> float:
        """Compute classification accuracy in [0.0, 1.0]."""
        probs = self.forward(x)
        preds = np.argmax(probs, axis=1)
        return float(np.mean(preds == y))


def load_partitioned_data(num_clients: int = 3, seed: int = 42) -> Tuple[list[Tuple[np.ndarray, np.ndarray]], Tuple[np.ndarray, np.ndarray]]:
    """Load digits dataset (1797 samples, 64 features) and partition among clients."""
    digits = load_digits()
    x = digits.data / 16.0  # normalize pixel values to [0, 1]
    y = digits.target

    rng = np.random.default_rng(seed)
    indices = rng.permutation(len(x))
    x, y = x[indices], y[indices]

    test_split = int(0.2 * len(x))
    x_test, y_test = x[:test_split], y[:test_split]
    x_train, y_train = x[test_split:], y[test_split:]

    client_data: list[Tuple[np.ndarray, np.ndarray]] = []
    splits = np.array_split(np.arange(len(x_train)), num_clients)
    for idxs in splits:
        client_data.append((x_train[idxs], y_train[idxs]))

    return client_data, (x_test, y_test)
