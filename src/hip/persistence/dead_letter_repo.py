"""Dead-letter store repository.

Persists unprocessable messages so nothing is silently dropped (docs/DESIGN.md 4).
The raw HL7 payload is PHI, so it is encrypted by the KeyManager before storage —
the dead-letter store is a PHI store, not a debug log (docs/DATA_MODEL.md).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hip.messaging.canonical.model import DeadLetterMessage
from hip.persistence.models import DeadLetterRow
from hip.security.keymanager import KeyManager


class DeadLetterRepository:
    def __init__(self, session: AsyncSession, key_manager: KeyManager) -> None:
        self._session = session
        self._keys = key_manager

    async def save(self, message: DeadLetterMessage) -> UUID:
        """Store a dead-letter entry with its raw payload encrypted."""
        row = DeadLetterRow(
            dead_letter_id=message.dead_letter_id,
            received_at=message.received_at,
            failure_stage=message.failure_stage.value,
            failure_reason_code=message.failure_reason.code,
            failure_reason_detail=message.failure_reason.detail,
            source=message.source,
            message_control_id=message.message_control_id,
            raw_ciphertext=self._keys.encrypt(message.raw_message.encode()),
        )
        self._session.add(row)
        return message.dead_letter_id
