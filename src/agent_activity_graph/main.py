from __future__ import annotations

import uvicorn


def run() -> None:
    uvicorn.run("agent_activity_graph.api.app:create_app", factory=True, reload=True)


if __name__ == "__main__":
    run()
