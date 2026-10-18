"""The mail port: one interface, three transports. The two messages it carries are rendered by the worker
(app/workers/render.py, P-TKT-06 "the worker process only"), so no money is formatted in the domain layer.

ONE PORT, THREE TRANSPORTS, chosen by MAIL_PROVIDER (no default, boot check 13):
  ses     Amazon SES, the AWS deployment (SRC-003 OPEN-EMAIL-01). boto3 is imported on the first send only.
  resend  Resend's HTTPS API, the Render copy (SRC-005 D-2). Standard library only (urllib), key from RESEND_SECRET.
  stub    sends nothing: one JSON line on stdout carrying the MIME message with the recipient address removed. Local
          development and tests only.
Every transport is handed the SAME rendered MIME message, so what a test reads off the stub is what SES would carry.

The port is `await transport.send(to, message) -> provider message id`. A refusal raises MailRefused carrying the
provider's own error text; the caller (app/workers) owns the timeout, because the timeout's bound and its
consequence (`failed` and retryable, P-TKT-05 exception 2a) are the caller's to record.

NOTHING HERE LOGS A MESSAGE. A log line may never carry the booking reference and the customer's address together
(FR-ADR-056) - the pair is enough to walk into a hall - and a reset message carries a live credential.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import sys
from email.message import EmailMessage
from email.policy import SMTP

from app.core.config import Settings

class MailRefused(Exception):
    """The provider answered and said no. str(exc) is the provider's own error text (P-TKT-05 exception 2)."""


# ---- transports --------------------------------------------------------------------------------------------------


class StubTransport:
    """MAIL_PROVIDER=stub: sends nothing. One JSON line per message on stdout, so the every-line-is-JSON rule holds and a
    test can parse the MIME text back with email.message_from_string. The recipient is removed first: the stub's line
    is a log line, and a reference beside an address is the pair FR-ADR-056 keeps out of every log."""

    def __init__(self, stream=None) -> None:
        self.stream = stream or sys.stdout
        self.sent = 0

    async def send(self, to: str, message: EmailMessage) -> str:
        shown = copy.deepcopy(message)
        shown.replace_header("To", "[REDACTED]")
        # A reset body carries the address and a live token; neither may reach a log line (S-TKT-15).
        mime = re.sub(r"token=[A-Za-z0-9_\-]+", "token=[REDACTED]", shown.as_string().replace(to, "[REDACTED]"))
        self.sent += 1
        self.stream.write(json.dumps({"logger": "app.mail.stub", "message": "stub mail transport: not sent",
                                      "mime": mime}, separators=(",", ":")) + "\n")
        self.stream.flush()
        return f"stub-{self.sent}"


class SesTransport:
    """MAIL_PROVIDER=ses. SendRawEmail with the rendered MIME message, so SES carries exactly what the stub shows.
    boto3 is imported on first use only (JC-R7-01): an api that never sends mail never loads it."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def _ses(self):
        if self._client is None:
            import boto3  # lazy, JC-R7-01
            from botocore.config import Config

            seconds = self.settings.SES_SEND_TIMEOUT_MS / 1000
            # max_attempts=1: the SDK's own retries would turn one 5 s bound into three (P-TKT-04 "the bound is the
            # value"). The retry that matters is the queue's redelivery, which survives the process dying.
            self._client = boto3.client("ses", region_name=self.settings.AWS_REGION,
                                        config=Config(retries={"max_attempts": 1, "mode": "standard"},
                                                      connect_timeout=seconds, read_timeout=seconds))
        return self._client

    async def send(self, to: str, message: EmailMessage) -> str:
        from botocore.exceptions import BotoCoreError, ClientError

        def call() -> str:
            out = self._ses().send_raw_email(Source=self.settings.SES_SENDER_ADDRESS, Destinations=[to],
                                             RawMessage={"Data": message.as_bytes(policy=SMTP)})
            return out["MessageId"]

        try:
            return await asyncio.to_thread(call)
        except ClientError as exc:
            err = exc.response.get("Error", {})
            raise MailRefused(f"SES {err.get('Code', 'error')}: {err.get('Message', '')}") from None
        except BotoCoreError as exc:
            raise MailRefused(f"SES {type(exc).__name__}: {exc}") from None


class ResendTransport:
    """MAIL_PROVIDER=resend, the Render copy (SRC-005 D-2): POST https://api.resend.com/emails with the standard library.
    The key is sent in the Authorization header and is never logged or put in an error message."""

    URL = "https://api.resend.com/emails"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, to: str, message: EmailMessage) -> str:
        import urllib.error
        import urllib.request

        text = message.get_body(("plain",)).get_content()
        html = message.get_body(("html",)).get_content()
        body = json.dumps({"from": message["From"], "to": [to], "subject": message["Subject"], "text": text, "html": html}).encode()
        req = urllib.request.Request(self.URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.settings.RESEND_SECRET}", "Content-Type": "application/json"})

        def call() -> str:
            with urllib.request.urlopen(req, timeout=self.settings.SES_SEND_TIMEOUT_MS / 1000) as resp:  # noqa: S310 - fixed https URL
                return json.loads(resp.read())["id"]

        try:
            return await asyncio.to_thread(call)
        except urllib.error.HTTPError as exc:
            # The provider's own words, bounded; the request (and so the key) is never echoed.
            raise MailRefused(f"Resend {exc.code}: {exc.read()[:200].decode('utf-8', 'replace')}") from None
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            raise MailRefused(f"Resend {type(exc).__name__}: {exc}") from None


def transport(settings: Settings):
    """The transport MAIL_PROVIDER names. Boot check 13 has already refused any other value."""
    return {"ses": SesTransport, "resend": ResendTransport, "stub": lambda s: StubTransport()}[settings.MAIL_PROVIDER](settings)
