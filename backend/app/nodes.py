from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import ValidationError

from app.config import Config, threshold_for_asset
from app.models import GraphState, GuardResult, ParsedSignal
from app.core.prompts import build_hermes_quant_prompt
from app.services import database, market_data, positions, retriever
from app.services.cloud_llm import generate_with_cloud_llm, parse_json_object
from app.services.paper_executor import build_paper_execution, emit_paper_execution

logger = logging.getLogger(__name__)


def _log_node(state: GraphState, node_name: str) -> None:
    logger.info("[RunID: %s] %s", state.get("run_id", "missing"), node_name)


def initialize_context(state: GraphState, config: Config) -> GraphState:
    _log_node(state, "initialize_context")
    next_state = dict(state)
    if not next_state.get("run_id"):
        raise ValueError("run_id is required")
    next_state.setdefault("asset_code", next(iter(config.assets), "000510"))
    next_state.setdefault("retry_count", 0)
    next_state.setdefault("errors", [])
    next_state["status"] = "running"
    return next_state


def fetch_market_data(state: GraphState, config: Config) -> GraphState:
    _log_node(state, "fetch_market_data")
    next_state = dict(state)
    snapshot = market_data.get_market_snapshot(config)
    next_state["market_snapshot"] = snapshot.model_dump(mode="json")
    return next_state


def route_market_state(state: GraphState) -> Literal["emergency", "sleep", "deep"]:
    _log_node(state, "route_market_state")
    snapshot = state.get("market_snapshot", {})
    vix = snapshot.get("vix")
    if vix is None:
        return "sleep"
    if float(vix) >= 35:
        return "emergency"
    if float(vix) < 12:
        return "sleep"
    return "deep"


def emergency_policy_node(state: GraphState) -> GraphState:
    _log_node(state, "emergency_policy_node")
    next_state = dict(state)
    asset_code = next_state["asset_code"]
    next_state["router_branch"] = "emergency"
    next_state["parsed_signal"] = ParsedSignal(
        asset_code=asset_code,
        action="Hold",
        confidence=1.0,
        reason="Emergency branch uses conservative Hold in iteration 2.",
        crash_override=True,
    ).model_dump(mode="json")
    return next_state


def sleep_node(state: GraphState) -> GraphState:
    _log_node(state, "sleep_node")
    next_state = dict(state)
    asset_code = next_state["asset_code"]
    next_state["router_branch"] = "sleep"
    next_state["parsed_signal"] = ParsedSignal(
        asset_code=asset_code,
        action="Hold",
        confidence=1.0,
        reason="Market state routed to sleep.",
    ).model_dump(mode="json")
    next_state["status"] = "slept"
    return next_state


def retrieve_context(state: GraphState) -> GraphState:
    _log_node(state, "retrieve_context")
    next_state = dict(state)
    next_state["router_branch"] = "deep"
    try:
        snippets = retriever.retrieve_similar_memories(next_state, top_k=3)
    except Exception as exc:
        errors = list(next_state.get("errors", []))
        errors.append(f"ChromaDB retrieval failed: {exc}")
        next_state["errors"] = errors
        snippets = []
    next_state["retrieved_snippets"] = snippets or [
        "ChromaDB 暂无可用历史相似新闻；本轮仅使用实时市场上下文。"
    ]
    return next_state


def reason_with_hermes(state: GraphState, config: Config) -> GraphState:
    _log_node(state, "reason_with_hermes")
    next_state = dict(state)
    retrieved_context = "\n\n".join(next_state.get("retrieved_snippets", []))
    market_context = str(next_state.get("market_snapshot", {}))
    prompt = build_hermes_quant_prompt(
        retrieved_context=retrieved_context,
        market_context=market_context,
    )
    try:
        raw_text = asyncio.run(generate_with_cloud_llm(config, prompt, allow_web_search_tools=True))
        next_state["hermes_raw_json"] = parse_json_object(raw_text)
    except Exception as exc:
        errors = list(next_state.get("errors", []))
        errors.append(str(exc))
        next_state["errors"] = errors
        next_state["hermes_raw_json"] = str(exc)
    return next_state


def _map_hermes_signal(raw: dict, fallback_asset_code: str) -> dict:
    allowed_fields = {"target_asset", "sentiment_score", "confidence", "reasoning"}
    extra_fields = set(raw) - allowed_fields
    if extra_fields:
        raise ValueError(f"Hermes output contained unsupported fields: {sorted(extra_fields)}")

    sentiment_score = float(raw.get("sentiment_score", 0.0))
    if sentiment_score > 0.2:
        action = "Buy"
    elif sentiment_score < -0.2:
        action = "Sell"
    else:
        action = "Hold"
    return {
        "asset_code": fallback_asset_code,
        "action": action,
        "confidence": raw.get("confidence", 0.0),
        "reason": raw.get("reasoning", "Hermes JSON signal mapped from sentiment_score."),
        "shares": 1.0,
        "cost_price": 1.0,
    }


def validate_llm_json(state: GraphState, config: Config) -> GraphState:
    _log_node(state, "validate_llm_json")
    next_state = dict(state)
    next_state.pop("parsed_signal", None)
    errors = list(next_state.get("errors", []))
    raw = next_state.get("hermes_raw_json")
    try:
        if not isinstance(raw, dict):
            raise ValueError("Hermes output is not a JSON object")
        signal = ParsedSignal.model_validate(
            _map_hermes_signal(raw, fallback_asset_code=next_state["asset_code"])
        )
        threshold = threshold_for_asset(config, signal.asset_code)
        if signal.confidence < threshold:
            signal = ParsedSignal(
                asset_code=signal.asset_code,
                action="Hold",
                confidence=signal.confidence,
                reason=f"Confidence {signal.confidence:.2f} below threshold {threshold:.2f}; fallback Hold.",
                shares=signal.shares,
                cost_price=signal.cost_price,
                extreme_stop_loss=signal.extreme_stop_loss,
                crash_override=signal.crash_override,
            )
        next_state["parsed_signal"] = signal.model_dump(mode="json")
    except (ValidationError, ValueError) as exc:
        next_state["retry_count"] = int(next_state.get("retry_count", 0)) + 1
        errors.append(str(exc))
        next_state["errors"] = errors
        if next_state["retry_count"] >= 2:
            next_state["parsed_signal"] = ParsedSignal(
                asset_code=next_state["asset_code"],
                action="Hold",
                confidence=0.0,
                reason="Invalid Hermes JSON after retries; fallback Hold.",
            ).model_dump(mode="json")
    return next_state


def route_after_validation(state: GraphState) -> Literal["retry", "guard"]:
    _log_node(state, "route_after_validation")
    if "parsed_signal" not in state and int(state.get("retry_count", 0)) < 2:
        return "retry"
    return "guard"


def position_policy_guard(state: GraphState, config: Config) -> GraphState:
    _log_node(state, "position_policy_guard")
    next_state = dict(state)
    signal = ParsedSignal.model_validate(next_state["parsed_signal"])
    if signal.action == "Buy":
        guard = GuardResult(
            allowed=True,
            final_action="Buy",
            reason="Buy allowed in paper mode; new lot will be inserted.",
            requested_shares=signal.shares,
            executable_shares=signal.shares,
        )
    elif signal.action == "Hold":
        guard = GuardResult(
            allowed=True,
            final_action="Hold",
            reason="Hold allowed in paper mode.",
            requested_shares=signal.shares,
        )
    else:
        asset = config.assets.get(signal.asset_code)
        is_c_class = asset is not None and asset.fund_class.upper() == "C"
        conn = database.connect(config.app.database_path)
        try:
            database.init_db(conn)
            evaluation = positions.evaluate_fifo_sell(
                conn,
                signal.asset_code,
                signal.shares,
                datetime.now(timezone.utc),
                allow_locked=(signal.extreme_stop_loss or signal.crash_override or not is_c_class),
            )
        finally:
            conn.close()
        executable = float(evaluation["executable_shares"])
        guard = GuardResult(
            allowed=executable > 0,
            final_action="Sell" if executable > 0 else "Hold",
            reason=str(evaluation["reason"]),
            requested_shares=float(evaluation["requested_shares"]),
            executable_shares=executable,
            blocked_shares=float(evaluation["blocked_shares"]),
            partial=bool(evaluation["partial"]),
        )
    next_state["guard_result"] = guard.model_dump(mode="json")
    return next_state


def paper_executor(state: GraphState, config: Config) -> GraphState:
    _log_node(state, "paper_executor")
    next_state = dict(state)
    signal = ParsedSignal.model_validate(next_state["parsed_signal"])
    guard = GuardResult.model_validate(next_state["guard_result"])
    execution = build_paper_execution(
        signal,
        guard,
        run_id=next_state["run_id"],
        router_branch=next_state.get("router_branch"),
    )

    conn = database.connect(config.app.database_path)
    try:
        database.init_db(conn)
        conn.execute("BEGIN")
        if guard.final_action == "Buy":
            positions.insert_lot(
                conn,
                asset_code=signal.asset_code,
                shares=guard.executable_shares,
                cost_price=signal.cost_price,
                buy_date=execution.timestamp,
                commit=False,
            )
        elif guard.final_action == "Sell" and guard.executable_shares > 0:
            asset = config.assets.get(signal.asset_code)
            is_c_class = asset is not None and asset.fund_class.upper() == "C"
            evaluation = positions.evaluate_fifo_sell(
                conn,
                signal.asset_code,
                signal.shares,
                execution.timestamp,
                allow_locked=(signal.extreme_stop_loss or signal.crash_override or not is_c_class),
            )
            executable = float(evaluation["executable_shares"])
            guard = GuardResult(
                allowed=executable > 0,
                final_action="Sell" if executable > 0 else "Hold",
                reason=str(evaluation["reason"]),
                requested_shares=float(evaluation["requested_shares"]),
                executable_shares=executable,
                blocked_shares=float(evaluation["blocked_shares"]),
                partial=bool(evaluation["partial"]),
            )
            execution = build_paper_execution(
                signal,
                guard,
                run_id=next_state["run_id"],
                router_branch=next_state.get("router_branch"),
            )
            updates = positions.execute_fifo_sell(
                conn,
                signal.asset_code,
                guard.executable_shares,
                execution.timestamp,
                allow_locked=(signal.extreme_stop_loss or signal.crash_override or not is_c_class),
                commit=False,
            )
            deducted = sum(float(update["deducted_shares"]) for update in updates)
            if deducted != guard.executable_shares:
                raise RuntimeError("FIFO sell deducted shares did not match guard executable shares")
        positions.append_paper_execution_log(
            conn,
            run_id=next_state["run_id"],
            timestamp=execution.timestamp,
            asset_code=signal.asset_code,
            router_branch=next_state.get("router_branch"),
            raw_signal=signal.model_dump(mode="json"),
            guard_result=guard.model_dump(mode="json"),
            final_action=guard.final_action,
            commit=False,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    emit_paper_execution(config, execution)
    next_state["guard_result"] = guard.model_dump(mode="json")
    next_state["paper_execution"] = execution.model_dump(mode="json")
    return next_state

def finalize(state: GraphState) -> GraphState:
    _log_node(state, "finalize")
    next_state = dict(state)
    next_state.setdefault("status", "completed")
    if next_state["status"] == "running":
        next_state["status"] = "completed"
    return next_state
