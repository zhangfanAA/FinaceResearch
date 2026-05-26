from datetime import datetime, timezone


def holding_days(buy_date: str, as_of: datetime | None = None) -> int:
    bought_at = datetime.fromisoformat(buy_date)
    checked_at = as_of or datetime.now(timezone.utc)
    if bought_at.tzinfo is None and checked_at.tzinfo is not None:
        bought_at = bought_at.replace(tzinfo=timezone.utc)
    if bought_at.tzinfo is not None and checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return max((checked_at - bought_at).days, 0)


def summarize_last_state(last_state: dict | None) -> dict | None:
    if last_state is None:
        return None
    guard_result = last_state.get("guard_result")
    return {
        "run_id": last_state.get("run_id"),
        "status": last_state.get("status"),
        "asset_code": last_state.get("asset_code"),
        "router_branch": last_state.get("router_branch"),
        "final_action": guard_result.get("final_action") if isinstance(guard_result, dict) else None,
    }
