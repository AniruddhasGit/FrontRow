"""The two real mail transports, one runnable check each, with no network (P-TKT-05 exception 2, S-TKT-08's 'SES error
response' mapping): SES through botocore's Stubber, Resend through a fake urlopen. Each proves the success value and
that a provider refusal becomes MailRefused carrying the provider's own words - and, for Resend, that the key rides only
in the Authorization header and never in the error text."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from app.domain.mail import MailRefused, ResendTransport, SesTransport
from app.workers.render import _message

pytestmark = pytest.mark.anyio
SETTINGS = SimpleNamespace(AWS_REGION="ap-south-1", SES_SENDER_ADDRESS="tickets@example.invalid", SES_SEND_TIMEOUT_MS=5000,
                           RESEND_SECRET="re_test_key_never_echoed")
TO = "name@example.com"


def _mail():
    return _message(SETTINGS.SES_SENDER_ADDRESS, TO, "Subject", "plain body\n", "<p>html body</p>\n")


async def test_ses_returns_the_message_id_and_maps_a_client_error_to_mail_refused():
    import boto3
    from botocore.stub import ANY, Stubber

    ses = SesTransport(SETTINGS)
    ses._client = boto3.client("ses", region_name=SETTINGS.AWS_REGION, aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(ses._client) as stub:
        stub.add_response("send_raw_email", {"MessageId": "ses-0001"},
                          {"Source": SETTINGS.SES_SENDER_ADDRESS, "Destinations": [TO], "RawMessage": {"Data": ANY}})
        stub.add_client_error("send_raw_email", service_error_code="MessageRejected",
                              service_message="Email address is not verified.")
        assert await ses.send(TO, _mail()) == "ses-0001"
        with pytest.raises(MailRefused) as refused:
            await ses.send(TO, _mail())
    assert str(refused.value) == "SES MessageRejected: Email address is not verified."


async def test_resend_sends_the_key_in_the_header_only_and_maps_an_http_error_to_mail_refused(monkeypatch):
    seen: list[urllib.request.Request] = []

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def ok(req, timeout):
        seen.append(req)
        return Answer(b'{"id": "re-0001"}')

    monkeypatch.setattr(urllib.request, "urlopen", ok)
    assert await ResendTransport(SETTINGS).send(TO, _mail()) == "re-0001"
    (req,) = seen
    assert req.get_header("Authorization") == f"Bearer {SETTINGS.RESEND_SECRET}"
    sent = json.loads(req.data)
    assert sent["to"] == [TO] and sent["text"] == "plain body\n" and SETTINGS.RESEND_SECRET not in req.data.decode()

    def refused(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 422, "Unprocessable", {}, io.BytesIO(b'{"message":"Invalid `to` field."}'))

    monkeypatch.setattr(urllib.request, "urlopen", refused)
    with pytest.raises(MailRefused) as exc:
        await ResendTransport(SETTINGS).send(TO, _mail())
    assert str(exc.value) == 'Resend 422: {"message":"Invalid `to` field."}'
    assert SETTINGS.RESEND_SECRET not in str(exc.value)
