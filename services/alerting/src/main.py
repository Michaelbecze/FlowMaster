"""Alerting service entry point.

Placeholder: only /healthz is implemented so the platform's docker-compose stack (and
User Story 1's independent test) can run end-to-end before User Story 4 (Threshold-Based
Alerting, tasks.md T081-T090) is built. Rules/events endpoints, the flow-records.v1
evaluator, and notification delivery are User Story 4's scope, not this MVP pass.
"""

from __future__ import annotations

from fastapi import FastAPI

from shared.logging import configure_logging

configure_logging("alerting")

app = FastAPI(title="FlowMaster Alerting Service")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
