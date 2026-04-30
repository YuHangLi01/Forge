"""Tests for seed_data.py safety guard."""

import pytest


def test_safe_user_id_demo_prefix_allowed() -> None:
    from scripts.seed_data import _require_safe_user_id

    _require_safe_user_id("demo_alice")  # should not raise


def test_safe_user_id_dev_prefix_allowed() -> None:
    from scripts.seed_data import _require_safe_user_id

    _require_safe_user_id("dev_tester1")  # should not raise


def test_safe_user_id_no_prefix_rejected() -> None:
    from scripts.seed_data import _require_safe_user_id

    with pytest.raises(ValueError, match="must start with"):
        _require_safe_user_id("alice")


def test_safe_user_id_prod_prefix_rejected() -> None:
    from scripts.seed_data import _require_safe_user_id

    with pytest.raises(ValueError, match="must start with"):
        _require_safe_user_id("prod_alice")


def test_safe_user_id_empty_rejected() -> None:
    from scripts.seed_data import _require_safe_user_id

    with pytest.raises(ValueError, match="must start with"):
        _require_safe_user_id("")
