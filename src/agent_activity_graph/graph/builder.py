from __future__ import annotations

import networkx as nx

from agent_activity_graph.sdk.events import WorkflowEvent


def build_activity_graph(events: list[WorkflowEvent]) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    ordered = sorted(events, key=lambda event: (event.timestamp, event.event_id))

    for event in ordered:
        graph.add_node(
            event.event_id,
            process_step=event.process_step,
            actor_type=event.actor_type.value,
            actor_name=event.actor_name,
            action_type=event.action_type,
            action_summary=event.action_summary,
            policy_status=event.policy_status.value,
            outcome_status=event.outcome_status.value,
            timestamp=event.timestamp,
            target_system=event.target_system,
        )

    for previous, current in zip(ordered, ordered[1:]):
        graph.add_edge(previous.event_id, current.event_id, relationship="next")

    for event in ordered:
        if event.parent_event_id:
            graph.add_edge(event.parent_event_id, event.event_id, relationship="caused_by")

    return graph

