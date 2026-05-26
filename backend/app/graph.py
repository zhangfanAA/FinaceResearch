from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from app.config import Config, load_config
from app.models import GraphState
from app import nodes


def build_graph(config: Config) -> Any:
    graph = StateGraph(GraphState)
    graph.add_node("initialize_context", lambda state: nodes.initialize_context(state, config))
    graph.add_node("fetch_market_data", lambda state: nodes.fetch_market_data(state, config))
    graph.add_node("emergency_policy_node", nodes.emergency_policy_node)
    graph.add_node("sleep_node", nodes.sleep_node)
    graph.add_node("retrieve_context", nodes.retrieve_context)
    graph.add_node("reason_with_hermes", lambda state: nodes.reason_with_hermes(state, config))
    graph.add_node("validate_llm_json", lambda state: nodes.validate_llm_json(state, config))
    graph.add_node("position_policy_guard", lambda state: nodes.position_policy_guard(state, config))
    graph.add_node("paper_executor", lambda state: nodes.paper_executor(state, config))
    graph.add_node("finalize", nodes.finalize)

    graph.add_edge(START, "initialize_context")
    graph.add_edge("initialize_context", "fetch_market_data")
    graph.add_conditional_edges(
        "fetch_market_data",
        nodes.route_market_state,
        {
            "emergency": "emergency_policy_node",
            "sleep": "sleep_node",
            "deep": "retrieve_context",
        },
    )
    graph.add_edge("emergency_policy_node", "position_policy_guard")
    graph.add_edge("sleep_node", "position_policy_guard")
    graph.add_edge("retrieve_context", "reason_with_hermes")
    graph.add_edge("reason_with_hermes", "validate_llm_json")
    graph.add_conditional_edges(
        "validate_llm_json",
        nodes.route_after_validation,
        {
            "retry": "reason_with_hermes",
            "guard": "position_policy_guard",
        },
    )
    graph.add_edge("position_policy_guard", "paper_executor")
    graph.add_edge("paper_executor", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def run_once(
    asset_code: str | None = None,
    config_path: str | Path = "config.yaml",
    run_id: str | None = None,
) -> GraphState:
    config = load_config(config_path)
    app = build_graph(config)
    initial_state: GraphState = {"run_id": run_id or uuid4().hex}
    if asset_code is not None:
        initial_state["asset_code"] = asset_code
    return app.invoke(initial_state)
