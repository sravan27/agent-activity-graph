from __future__ import annotations

from collections.abc import Iterable

import httpx

from agent_activity_graph.sdk.events import EventIngestionResponse, WorkflowEvent


class AgentActivityGraphClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def send_event(self, event: WorkflowEvent) -> EventIngestionResponse:
        with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
            response = client.post("/api/events", json=event.model_dump(mode="json"))
            response.raise_for_status()
            return EventIngestionResponse.model_validate(response.json())

    def send_events(self, events: Iterable[WorkflowEvent]) -> list[EventIngestionResponse]:
        return [self.send_event(event) for event in events]

