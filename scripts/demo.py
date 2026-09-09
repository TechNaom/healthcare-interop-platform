"""Demo: exercise a running gateway — create, read, and search a Patient.

Point it at a live stack (``docker compose up``). It mints an HS256 token from
HIP_JWT_SECRET (the same secret the gateway uses) carrying read/write/full roles,
then POSTs a Patient, reads it back, and searches by identifier via the blind
index. Synthetic data only (ADR-005).

    HIP_JWT_SECRET=... uv run python scripts/demo.py
"""

from __future__ import annotations

import os
import sys

import httpx
import jwt

GATEWAY = os.environ.get("HIP_GATEWAY_URL", "http://localhost:8000")
SECRET = os.environ.get("HIP_JWT_SECRET")

_PATIENT = {
    "resourceType": "Patient",
    "identifier": [{"system": "HOSP", "value": "DEMO-1", "type": {"coding": [{"code": "MR"}]}}],
    "name": [{"use": "official", "family": "DEMO", "given": ["ALEX"]}],
    "gender": "other",
    "birthDate": "1991-02-03",
}


def _token() -> str:
    if not SECRET:
        sys.exit("set HIP_JWT_SECRET to the gateway's JWT secret")
    claims = {
        "sub": "demo-user",
        "realm_access": {"roles": ["fhir:read", "fhir:write", "phi:full"]},
    }
    return jwt.encode(claims, SECRET, algorithm="HS256")


def main() -> None:
    headers = {"Authorization": f"Bearer {_token()}"}
    with httpx.Client(base_url=GATEWAY, timeout=10) as client:
        print("health   :", client.get("/healthz").json())

        created = client.post("/fhir/Patient", json=_PATIENT, headers=headers)
        location = created.headers.get("Location", "")
        print("create   :", created.status_code, location)

        read = client.get(location, headers=headers)
        print("read     :", read.status_code, read.json()["name"][0]["family"])

        found = client.get("/fhir/Patient", params={"identifier": "HOSP|DEMO-1"}, headers=headers)
        print("search   :", found.status_code, "total =", found.json()["total"])


if __name__ == "__main__":
    main()
