"""The queue interface - ONE implementation over both SQS (AWS) and ElasticMQ (local compose), FR-ADR-059.

ElasticMQ speaks the SQS API, so the only difference between the two is the endpoint, and the endpoint is read off
QUEUE_URL itself (`https://sqs.ap-south-1.amazonaws.com/...` or `http://elasticmq:9324/...`). There is no second
code path to drift.  ZONE B: the client edits this when the queue changes.

A message is (topic, body). The topic travels as an SQS message ATTRIBUTE, not in the body, because the body of a
password_reset.send message must have exactly the key set P-TKT-12 publishes (S-TKT-15), and the worker must read the
topic before it parses anything else (P-TKT-05).

boto3 is imported on the first call only (JC-R7-01): the Render copy (no queue) and an api that never sends never
load it, and that is ~20-30 MB of resident memory on a 1 GB host.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.config import Settings


@dataclass
class Message:
    id: str  # the queue's own message id: the worker's job_id (S-XCT-25)
    topic: str | None  # None when the attribute is missing - an unknown topic, never deleted (P-TKT-05)
    body: dict | None  # None when the body is not a JSON object - same treatment
    receipt_handle: str


class SqsQueue:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.QUEUE_URL
        self.settings = settings
        self._send = None
        self._recv = None

    def _client(self, read_timeout_s: float):
        import boto3  # lazy, JC-R7-01
        from botocore.config import Config

        parts = urlsplit(self.url)
        return boto3.client(
            "sqs",
            region_name=self.settings.AWS_REGION,
            # The endpoint comes from QUEUE_URL, so one variable points the same code at SQS or at ElasticMQ.
            endpoint_url=f"{parts.scheme}://{parts.netloc}",
            # max_attempts=1: SDK retries would turn one bounded call into three (P-TKT-04 "the bound is the value").
            # The relay is the retry, and it survives the process dying.
            config=Config(retries={"max_attempts": 1, "mode": "standard"}, connect_timeout=read_timeout_s, read_timeout=read_timeout_s),
        )

    async def send(self, topic: str, body: dict) -> None:
        """One SendMessage. Bounded by QUEUE_SEND_TIMEOUT_MS at the socket; the caller also bounds the await."""
        if self._send is None:
            self._send = self._client(self.settings.QUEUE_SEND_TIMEOUT_MS / 1000)
        await asyncio.to_thread(self._send.send_message, QueueUrl=self.url, MessageBody=json.dumps(body, separators=(",", ":")),
                                MessageAttributes={"topic": {"DataType": "String", "StringValue": topic}})

    async def receive(self, max_messages: int) -> list[Message]:
        """One long poll (QUEUE_POLL_WAIT_SECONDS): short polling burns the free-tier request allowance on empty receives."""
        wait = self.settings.QUEUE_POLL_WAIT_SECONDS
        if self._recv is None:
            # The read timeout must outlast the long poll, or every empty receive is reported as a network error.
            self._recv = self._client(wait + 10)
        out = await asyncio.to_thread(self._recv.receive_message, QueueUrl=self.url, MaxNumberOfMessages=max_messages,
                                      WaitTimeSeconds=wait, MessageAttributeNames=["topic"])
        return [_parse(m) for m in out.get("Messages", [])]

    async def depth(self) -> int:
        """ApproximateNumberOfMessages, for /metrics queue_depth (cached by app.core.metrics.QueueDepth)."""
        if self._send is None:
            self._send = self._client(self.settings.QUEUE_SEND_TIMEOUT_MS / 1000)
        out = await asyncio.to_thread(self._send.get_queue_attributes, QueueUrl=self.url, AttributeNames=["ApproximateNumberOfMessages"])
        return int(out["Attributes"]["ApproximateNumberOfMessages"])

    async def remove(self, message: Message) -> None:
        if self._recv is None:
            self._recv = self._client(self.settings.QUEUE_POLL_WAIT_SECONDS + 10)
        await asyncio.to_thread(self._recv.delete_message, QueueUrl=self.url, ReceiptHandle=message.receipt_handle)


def _parse(raw: dict) -> Message:
    topic = (raw.get("MessageAttributes") or {}).get("topic", {}).get("StringValue")
    try:
        body = json.loads(raw.get("Body", ""))
    except ValueError:
        body = None
    return Message(id=raw["MessageId"], topic=topic, body=body if isinstance(body, dict) else None,
                   receipt_handle=raw["ReceiptHandle"])
