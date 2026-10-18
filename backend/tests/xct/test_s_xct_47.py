"""S-XCT-47 (PRD P-XCT-31): no artificial-intelligence feature. Phase 1's share.

Not here: the socket-level allowlist over the whole suite and the "exactly three boto3 clients"
clause (no boto3 client exists until Phase 5), and the listings ORDER BY (Phase 3).
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
