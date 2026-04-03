from __future__ import annotations

from agent_activity_graph.graph.builder import build_activity_graph
from agent_activity_graph.sdk.events import GraphEdge, GraphNode, PolicyStatus, WorkflowEvent, WorkflowGraphSnapshot


def build_graph_snapshot(workflow_id: str, events: list[WorkflowEvent]) -> WorkflowGraphSnapshot:
    graph = build_activity_graph(events)
    ordered = sorted(events, key=lambda event: (event.timestamp, event.event_id))

    actor_transitions = 0
    previous_actor_type = None
    for event in ordered:
        if previous_actor_type and previous_actor_type != event.actor_type:
            actor_transitions += 1
        previous_actor_type = event.actor_type

    nodes = [
        GraphNode(
            event_id=event.event_id,
            label=f"{event.process_step}: {event.action_type}",
            timestamp=event.timestamp,
            process_step=event.process_step,
            actor_type=event.actor_type.value,
            actor_name=event.actor_name,
            action_type=event.action_type,
            policy_status=event.policy_status.value,
            outcome_status=event.outcome_status.value,
            target_system=event.target_system,
        )
        for event in ordered
    ]
    edges = [
        GraphEdge(
            source_event_id=source,
            target_event_id=target,
            relationship=data["relationship"],
        )
        for source, target, _, data in graph.edges(keys=True, data=True)
    ]

    systems = sorted({event.target_system for event in ordered if event.target_system})
    blocked_event_ids = [
        event.event_id
        for event in ordered
        if event.policy_status == PolicyStatus.BLOCKED
    ]
    return WorkflowGraphSnapshot(
        workflow_id=workflow_id,
        node_count=len(nodes),
        edge_count=len(edges),
        actor_transitions=actor_transitions,
        systems_touched=systems,
        blocked_event_ids=blocked_event_ids,
        nodes=nodes,
        edges=edges,
    )

