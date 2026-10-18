"""S-SCP-12 (P-SCP-12): no card data and no real provider exist anywhere, and the demonstration line renders.

The rendered-screen clauses (the checkout's inputs, the footer inside contentinfo on five pages) are asserted where
they can be without a browser: frontend/src/features/booking/checkout.test.mjs."""

from __future__ import annotations

import importlib
import pkgutil
import re
import socket
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_settings import BaseSettings

import app
from tests.pay.kit import FIVE, api, clock_at, confirm, hold, owner_sql, redis_url, user, world7

pytestmark = pytest.mark.anyio
REPO = Path("/repo")
# Assembled from fragments at run time, so this module's own source cannot match it (backend/tests stays in scope).
CARD = re.compile("|".join(["card" + "_?number", "c" + "vv", "c" + "vc", "expiry" + "_?(month|year)", "card" + "holder"]), re.IGNORECASE)
FIELD = re.compile("|".join(["card" + "_?number", "^pan$", "c" + "vv", "c" + "vc", "expiry", "expiration", "card" + "holder"]),
                   re.IGNORECASE)
PROVIDERS = re.compile("stripe|razorpay|payu|paypal|braintree|adyen", re.IGNORECASE)
SUFFIXES = (".py", ".ts", ".tsx", ".mjs", ".css", ".sql", ".json", ".md", ".html", ".txt")


def _hits(pattern: re.Pattern, *paths: Path) -> list[str]:
    files = [p for root in paths for p in ([root] if root.is_file() else root.rglob("*")) if p.is_file() and p.suffix in SUFFIXES]
    return [f"{p.relative_to(REPO)}:{n}" for p in files
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1) if pattern.search(line)]


def _models() -> list[type[BaseModel]]:
    for info in pkgutil.walk_packages(app.__path__, "app."):
        importlib.import_module(info.name)
    seen, todo = [], [BaseModel]
    while todo:
        for sub in todo.pop().__subclasses__():
            todo.append(sub)
            if sub.__module__.startswith("app.") and not issubclass(sub, BaseSettings):
                seen.append(sub)
    return seen


def test_no_request_model_declares_a_card_field():
    models = _models()
    assert models, "no model found - a vacuous pass is not a pass"
    assert [f"{m.__name__}.{f}" for m in models for f in m.model_fields if FIELD.search(f)] == []


def test_no_card_shaped_text_in_the_four_trees_or_the_tests():
    trees = [REPO / "backend" / "app", REPO / "backend" / "migrations", REPO / "frontend" / "src", REPO / "scripts", REPO / "backend" / "tests"]
    assert _hits(CARD, *trees) == []


def test_no_real_provider_is_named():
    paths = [REPO / "backend" / "app", REPO / "frontend" / "src", REPO / "scripts", REPO / "backend" / "requirements.txt",
             REPO / "frontend" / "package.json"]
    assert _hits(PROVIDERS, *paths) == []


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_a_confirmed_booking_captured_in_order_and_nothing_left_the_process(world, monkeypatch):
    db = world["db"]
    u = user(db)
    allowed = {re.match(r"redis://([^:/]+)", redis_url()).group(1)}
    outbound: list[str] = []
    real = socket.socket.connect

    def recording(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in allowed and not str(host).startswith(("172.", "127.")):
            outbound.append(str(host))
        return real(self, address)

    monkeypatch.setattr(socket.socket, "connect", recording)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        r = await confirm(c, u, h["hold_token"])
    assert r.status_code == 201
    state, p, a, cap = owner_sql(db, "SELECT state, pending_at, authorized_at, captured_at FROM payment WHERE id = "
                                     "(SELECT payment_id FROM booking WHERE id = %s)", (r.json()["booking_id"],))[0]
    assert state == "captured" and p is not None and a is not None and cap is not None and p <= a <= cap
    assert outbound == []
