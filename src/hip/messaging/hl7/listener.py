"""HL7 v2 ingestion transport: MLLP / HTTP / file-drop.

Maps to ``messaging.hl7.listener`` in docs/DESIGN.md section 1. A custom asyncio
MLLP listener handles the ``<VT>msg<FS><CR>`` framing (docs/TECH_STACK.md — no
dedicated MLLP dependency is warranted). Emits raw messages to the parser and
returns ACK/NACK to the sender. Implemented in Phase 4-5. Phase 0 placeholder.
"""
