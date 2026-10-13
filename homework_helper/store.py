"""Cloud storage in Amazon DynamoDB, for when Homework Helper runs on AWS.

One table holds four kinds of item, told apart by the partition key:

  pk="sent"          sk=<reminder key>   reminders already sent (replaces
                                         the local reminders_sent.json)
  pk="notification"  sk=<time>#<key>     reminders waiting to be heard, like
                                         unread Alexa notifications
  pk="name"          sk=<Canvas title>   short spoken name for that title
  pk="settings"      sk="plan"           the student's changes to their plan
                                         (busy times, bedtime), as JSON

Sent reminders and notifications carry an `expires` time, so DynamoDB's TTL
cleans up old records. Names and settings are kept.
"""

import json
import os
from datetime import datetime

from homework_helper.reminders import FORGET_AFTER


def table(name: str | None = None):
    import boto3
    return boto3.resource("dynamodb").Table(name or os.environ["HOMEWORK_TABLE"])


def _expires(now: datetime) -> int:
    return int((now + FORGET_AFTER).timestamp())


class DynamoSentLog:
    """Same job as reminders.SentLog, kept in DynamoDB."""

    def __init__(self, tbl):
        self.table = tbl

    def __contains__(self, key: str) -> bool:
        return "Item" in self.table.get_item(Key={"pk": "sent", "sk": key})

    def mark(self, keys: list[str], now: datetime) -> None:
        for key in keys:
            self.table.put_item(Item={"pk": "sent", "sk": key, "at": now.isoformat(),
                                      "expires": _expires(now)})


class DynamoNames:
    """Same job as names.FileNames, kept in DynamoDB."""

    def __init__(self, tbl):
        self.table = tbl

    def load(self) -> dict[str, str]:
        return {item["sk"]: item["name"] for item in _query(self.table, "name")}

    def save(self, new: dict[str, str]) -> None:
        with self.table.batch_writer() as batch:
            for title, name in new.items():
                batch.put_item(Item={"pk": "name", "sk": title, "name": name})


class DynamoSettings:
    """Same job as plan_settings.FileSettings, kept in DynamoDB."""

    def __init__(self, tbl):
        self.table = tbl

    def load(self) -> dict:
        item = self.table.get_item(Key={"pk": "settings", "sk": "plan"}).get("Item")
        return json.loads(item["data"]) if item else {}

    def save(self, data: dict) -> None:
        self.table.put_item(Item={"pk": "settings", "sk": "plan", "data": json.dumps(data)})


def _query(tbl, pk: str) -> list[dict]:
    """Every item under one partition key, following DynamoDB's pages."""
    from boto3.dynamodb.conditions import Key
    items, start = [], {}
    while True:
        page = tbl.query(KeyConditionExpression=Key("pk").eq(pk), **start)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            return items
        start = {"ExclusiveStartKey": page["LastEvaluatedKey"]}


class Inbox:
    """Reminders waiting to be heard, oldest first."""

    def __init__(self, tbl):
        self.table = tbl

    def add(self, items: list[tuple[str, str]], now: datetime) -> None:
        """Adds (reminder key, spoken text) pairs."""
        for key, text in items:
            self.table.put_item(Item={"pk": "notification", "sk": f"{now.isoformat()}#{key}",
                                      "text": text, "expires": _expires(now)})

    def _unread(self) -> list[dict]:
        return _query(self.table, "notification")

    def count(self) -> int:
        return len(self._unread())

    def take(self) -> list[str]:
        """Reads every unread notification and removes it."""
        items = self._unread()
        for item in items:
            self.table.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
        return [item["text"] for item in items]
