from typing import get_args

import pytest

from app.tools import (
    COMPONENT_TEAMS,
    Component,
    get_component_owner,
    normalize_component,
)


def test_component_type_matches_table():
    assert set(get_args(Component)) == set(COMPONENT_TEAMS)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("payment", "payment"),
        ("Payment", "payment"),
        ("Payment Gateway", "payment"),
        ("payment_gateway", "payment"),
        ("payment processing", "payment"),
        ("payments", "payment"),
        ("product search", "search"),
        ("Google login authentication", "authentication"),
        ("auth", "authentication"),
        ("email", "notification"),
        ("  PAYMENT  ", "payment"),
    ],
)
def test_normalize_component_resolves_free_form(raw, expected):
    assert normalize_component(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "billing", "cart", 42, ["payment"]])
def test_normalize_component_rejects_unmapped(raw):
    assert normalize_component(raw) is None


def test_get_component_owner_resolves_free_form():
    assert get_component_owner("Payment Gateway", "production") == "Payment Team"
    assert get_component_owner("product search", "staging") == "Search Team"


def test_payment_production_owner():
    assert get_component_owner("payment", "production") == "Payment Team"


def test_checkout_production_owner():
    assert get_component_owner("checkout", "production") == "Checkout Team"


def test_authentication_production_owner():
    assert get_component_owner("authentication", "production") == "Identity Team"


def test_unknown_owner():
    assert get_component_owner("unknown", "production") == "Unknown Team"
