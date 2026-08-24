"""OS-agnostic platform shim.

The roadmap calls for a single ``platform/`` layer so no OS-specific assumption
leaks into core logic (ADR-003). Renamed to ``hip.platform`` in code to avoid
shadowing the stdlib ``platform`` module. Anything that would otherwise reach
for an absolute path, an environment quirk, or an OS branch goes through here.
"""
