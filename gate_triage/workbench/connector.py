"""Read-only Terminal49 connector boundary.

This adapter is not enabled for the anonymous synthetic demo. Provider fields
are preserved, including missing versus null holds. Site telemetry is never
fabricated from a carrier weight or equipment type.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select

from .db import ProviderInbox, get_database


class ConnectorError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code, self.message, self.retryable = code, message, retryable
        super().__init__(message)


@dataclass
class Terminal49Connector:
    token: str | None = None
    base_url: str = "https://api.terminal49.com/v2"

    def __post_init__(self):
        self.token = self.token or os.getenv("T49_API_KEY") or os.getenv("TERMINAL49_API_KEY")

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def get_container(self, provider_id: str) -> dict:
        # Resource IDs are restricted before constructing a path; no arbitrary
        # URL or alternate upstream can be supplied by a browser.
        if not provider_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in provider_id):
            raise ConnectorError("VALIDATION_ERROR", "Invalid provider resource ID.")
        return self._get(f"/containers/{provider_id}")

    def _get(self, path: str) -> dict:
        if not self.token:
            raise ConnectorError("SOURCE_NOT_CONFIGURED", "Terminal49 credentials are not configured.")
        request = urllib.request.Request(self.base_url + path, headers={"Authorization": f"Token {self.token}", "Accept": "application/vnd.api+json", "User-Agent": "GateTriageWorkbench/1"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ConnectorError("SOURCE_UNAVAILABLE", "The provider response exceeded the configured limit.", True)
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise ConnectorError("SOURCE_PERMISSION_DENIED", "The configured account cannot read this resource.") from None
            if exc.code == 429:
                raise ConnectorError("SOURCE_RATE_LIMITED", "The provider request budget is temporarily exhausted.", True) from None
            raise ConnectorError("SOURCE_UNAVAILABLE", "Terminal49 could not complete this read.", True) from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            raise ConnectorError("SOURCE_UNAVAILABLE", "Terminal49 could not complete this read.", True) from None

    @staticmethod
    def normalize_container(resource: dict, *, received_at: str | None = None) -> dict:
        attributes = resource.get("attributes")
        if not isinstance(attributes, dict):
            raise ConnectorError("SOURCE_SCHEMA_ERROR", "The provider container attributes are missing.")
        retained = ("number", "availability_known", "available_for_pickup", "holds_at_pod_terminal", "fees_at_pod_terminal", "pickup_lfd", "import_deadlines", "pickup_appointment_at", "pod_discharged_at", "pod_full_out_at", "location_at_pod_terminal", "equipment_type", "equipment_length", "equipment_height", "weight_in_lbs", "terminal_checked_at")
        return {"id": resource.get("id"), "attributes": {key: attributes[key] for key in retained if key in attributes}, "relationships": resource.get("relationships", {}), "origin_kind": "terminal49_live", "received_at": received_at or datetime.now(timezone.utc).isoformat(), "unknown_attributes": {key: value for key, value in attributes.items() if key not in retained}, "limitations": {"weight_is_not_independent_scale": True, "equipment_type_does_not_report_temperature": True, "availability_is_not_release_authority": True}}


def verify_webhook(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or len(raw_body) > 1_000_000:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    candidate = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, candidate)


def install_webhook(router) -> None:
    @router.post("/webhooks/terminal49/{connection}", status_code=202)
    async def terminal49_webhook(connection: str, request: Request):
        from .api import ApiError, envelope, respond
        import uuid
        secret = os.getenv("T49_WEBHOOK_SECRET")
        expected_connection = os.getenv("T49_WEBHOOK_CONNECTION", "default")
        if not secret or connection != expected_connection:
            raise ApiError(503, "SOURCE_NOT_CONFIGURED", "This provider webhook is not enabled.")
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                oversized = int(content_length) > 1_000_000
            except ValueError:
                raise ApiError(422, "VALIDATION_ERROR", "The request size header is invalid.")
            if oversized:
                raise ApiError(413, "PAYLOAD_TOO_LARGE", "This webhook exceeds the configured size limit.")
        chunks = bytearray()
        async for chunk in request.stream():
            if len(chunks) + len(chunk) > 1_000_000:
                raise ApiError(413, "PAYLOAD_TOO_LARGE", "This webhook exceeds the configured size limit.")
            chunks.extend(chunk)
        raw = bytes(chunks)
        if not verify_webhook(raw, request.headers.get("X-T49-Webhook-Signature"), secret):
            raise ApiError(401, "INVALID_SIGNATURE", "The provider signature could not be verified.")
        try:
            payload = json.loads(raw)
            event_id = str(payload["data"]["id"])
        except (json.JSONDecodeError, KeyError, TypeError):
            raise ApiError(422, "SOURCE_SCHEMA_ERROR", "This notification does not contain a valid event ID.")
        body_hash = hashlib.sha256(raw).hexdigest()
        database = get_database()
        with database.write_lock, database.session() as session:
            row = session.scalar(select(ProviderInbox).where(ProviderInbox.connection == connection, ProviderInbox.event_id == event_id))
            if row:
                if row.body_hash != body_hash:
                    # Keep the original record, explicitly record quarantine.
                    row.status = "quarantined_id_conflict"
                    session.flush()
                    # Return a response instead of raising: quarantine must commit.
                    return respond(envelope({"accepted": False, "status": "quarantined_id_conflict"}), 409)
                return respond(envelope({"accepted": True, "duplicate": True, "status": row.status}), 202)
            session.add(ProviderInbox(id=str(uuid.uuid4()), connection=connection, event_id=event_id, body_hash=body_hash, payload=payload, status="stored_unprojected"))
        return respond(envelope({"accepted": True, "status": "stored_unprojected", "note": "Stored securely; no anonymous live workspace projection is enabled."}), 202)
