"""Trivial test for verifying Python test environment."""


def test_trivial_truth() -> None:
    """Verify basic assertion and arithmetic."""
    assert 1 + 1 == 2


def test_module_imports() -> None:
    """Verify local package modules import cleanly."""
    import ledger
    import sim

    assert ledger is not None
    assert sim is not None
