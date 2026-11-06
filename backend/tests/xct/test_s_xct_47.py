"""S-XCT-47 (PRD P-XCT-31): no artificial-intelligence feature.

Asserted: the boto3 clients are only s3, sqs and ses; the model vocabulary sweep; ?sort=score on the listings answers
422 VALIDATION_FAILED.

Not here: (1) the socket-level allowlist over the whole test suite, failing on any other host. (2) The listings ORDER BY
being "exactly created_at DESC, id DESC" under a before_cursor_execute listener: the code orders by published_at DESC,
id DESC (app/domain/browse/catalogue.py), which P-BRW-03, S-BRW-03 and the generated contract specify. The two
documents disagree, so this clause needs a Bible amendment, not a code change.
"""

from __future__ import annotations

from ._support import rg


def test_model_vocabulary_appears_only_where_it_says_there_is_none():
    pattern = r"openai|anthropic|bedrock|sagemaker|huggingface|cohere|vertexai|embedding|inference|recommend"
    hits = rg(pattern, "backend/app", "backend/migrations", "frontend/src", ignore_case=True)
    assert [h for h in hits if "no artificial-intelligence feature" not in h[2]] == []


def test_no_boto3_client_outside_s3_sqs_ses():
    hits = rg(r"boto3\.client\(['\"](?!s3['\"]|sqs['\"]|ses['\"])", "backend/app")
    assert hits == []


def test_a_sort_outside_the_fixed_allowlist_is_422(valid_env, clock):
    from fastapi.testclient import TestClient

    from app.core.config import load_settings
    from app.main import create_app
    from tests.test_health import ok_probe

    with TestClient(create_app(load_settings(), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])) as c:
        r = c.get("/api/movies", params={"sort": "score"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED")
