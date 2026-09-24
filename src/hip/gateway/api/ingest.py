"""HTTP HL7 v2 ingestion transport.

Maps to ``gateway.api.ingest`` in docs/DESIGN.md 1. A second inbound transport
alongside the MLLP listener: an HL7 v2 message is POSTed as the raw request body
and the HL7 ``ACK`` (AA/AE/AR) is returned as the response body. Both transports
funnel into the same ``messaging.hl7.listener.ingest`` pipeline (parse -> route
-> map -> encrypted persist -> acknowledge), so behaviour is identical regardless
of how a message arrives (ADR-001, one canonical path).

Why HTTP as well as MLLP: many senders (and cloud load balancers / API gateways)
speak HTTPS far more readily than a raw MLLP socket, and it lets the same
message flow ride the gateway's existing auth, RBAC, rate limiting, tracing, and
metrics. The response is the HL7 ACK itself (``application/hl7-v2``); the HTTP
status mirrors the ACK for HTTP-native clients (200 accepted, 422 rejected).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hip.gateway.auth import Principal
from hip.gateway.deps import (
    get_key_manager,
    get_optional_blind_indexer,
    get_session_factory,
    require_role,
)
from hip.messaging.hl7 import ack
from hip.messaging.hl7.listener import ingest
from hip.security.blind_index import BlindIndexer
from hip.security.keymanager import KeyManager

router = APIRouter(prefix="/hl7", tags=["ingest"])

# HL7 v2 ER7 (pipe-and-hat) media type for both request and ACK response.
_HL7_MEDIA_TYPE = "application/hl7-v2"

# RBAC: submitting HL7 into the pipeline is its own privilege, distinct from the
# FHIR read/write roles (SRS 5.1).
_INGEST_ROLE = "hl7:ingest"

# Max inbound message size — a guard against a single request exhausting memory.
# HL7 v2 messages are typically a few KB; 1 MiB is generous headroom.
_MAX_MESSAGE_BYTES = 1024 * 1024

IngestPrincipalDep = Annotated[Principal, Depends(require_role(_INGEST_ROLE))]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
KeyDep = Annotated[KeyManager, Depends(get_key_manager)]
OptBlindDep = Annotated[BlindIndexer | None, Depends(get_optional_blind_indexer)]


@router.post("/v2", response_class=Response)
async def ingest_hl7_v2(
    request: Request,
    _principal: IngestPrincipalDep,
    session_factory: SessionFactoryDep,
    key_manager: KeyDep,
    blind_indexer: OptBlindDep,
) -> Response:
    """Ingest one HL7 v2 message from the request body; return its HL7 ACK.

    The message is persisted (encrypted) on accept and dead-lettered on failure,
    exactly as over MLLP. A too-large or non-decodable body is rejected with an
    HL7 ``AR`` NACK, never dropped.
    """
    body = await request.body()
    if len(body) > _MAX_MESSAGE_BYTES:
        nack = ack.build_nack_unparseable("MESSAGE_TOO_LARGE")
        return _ack_response(nack, accepted=False)

    try:
        raw = body.decode("utf-8")
    except UnicodeDecodeError:
        nack = ack.build_nack_unparseable("INVALID_ENCODING", "body is not valid UTF-8")
        return _ack_response(nack, accepted=False)

    result = await ingest(raw, session_factory, key_manager, blind_indexer)
    return _ack_response(result.ack_message, accepted=result.ack_code is ack.AckCode.AA)


def _ack_response(ack_message: str, *, accepted: bool) -> Response:
    """Wrap an HL7 ACK as the HTTP response — 200 on accept, 422 on reject.

    The ACK body is returned in both cases so an HL7-aware client can read the
    MSA-1 code directly; the HTTP status is a convenience for HTTP-native ones.
    """
    status_code = 200 if accepted else 422
    return Response(content=ack_message, media_type=_HL7_MEDIA_TYPE, status_code=status_code)
