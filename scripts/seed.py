"""Seed a running gateway with a synthetic patient population (demo / load prep).

Generates ``--count`` reproducible synthetic Patients (``hip.synthetic``) and
POSTs them to a live gateway, minting an HS256 token from HIP_JWT_SECRET (the
same secret the gateway uses). Synthetic data only (ADR-005).

    HIP_JWT_SECRET=... uv run python scripts/seed.py --count 100
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx
import jwt

from hip.synthetic import SyntheticPopulation

GATEWAY = os.environ.get("HIP_GATEWAY_URL", "http://localhost:8000")
SECRET = os.environ.get("HIP_JWT_SECRET")
_HTTP_CREATED = 201


def _token() -> str:
    if not SECRET:
        sys.exit("set HIP_JWT_SECRET to the gateway's JWT secret")
    claims = {"sub": "seed-script", "realm_access": {"roles": ["fhir:write"]}}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic Patients into the gateway.")
    parser.add_argument("--count", type=int, default=100, help="number of patients to create")
    parser.add_argument("--seed", type=int, default=0, help="PRNG seed for reproducibility")
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {_token()}"}
    population = SyntheticPopulation(seed=args.seed)
    created = 0
    with httpx.Client(base_url=GATEWAY, timeout=30) as client:
        for person in population.people(args.count):
            resp = client.post(
                "/fhir/Patient", json=population.fhir_patient(person), headers=headers
            )
            if resp.status_code == _HTTP_CREATED:
                created += 1
            else:
                print(f"warn: {person.mrn} -> {resp.status_code} {resp.text[:120]}")
    print(f"seeded {created}/{args.count} synthetic patients into {GATEWAY}")


if __name__ == "__main__":
    main()
