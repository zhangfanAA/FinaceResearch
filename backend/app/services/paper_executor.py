import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from app.config import Config
from app.models import GuardResult, PaperExecution, ParsedSignal


def build_paper_execution(
    signal: ParsedSignal,
    guard: GuardResult,
    run_id: str,
    router_branch: str | None,
) -> PaperExecution:
    return PaperExecution(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc),
        asset_code=signal.asset_code,
        router_branch=router_branch,
        requested_action=signal.action,
        executed_action=guard.final_action,
        quantity=guard.executable_shares if guard.final_action in {"Buy", "Sell"} else None,
        reason=guard.reason,
        paper_only=True,
    )


def write_paper_execution(log_path: str | Path, execution: PaperExecution) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(execution.model_dump_json() + "\n")


def notify_webhook(config: Config, execution: PaperExecution) -> None:
    if not config.webhook.enabled or not config.webhook.url:
        return
    try:
        requests.post(
            config.webhook.url,
            json=json.loads(execution.model_dump_json()),
            timeout=config.webhook.timeout_seconds,
        )
    except Exception:
        return


def emit_paper_execution(config: Config, execution: PaperExecution) -> None:
    write_paper_execution(config.app.paper_log_path, execution)
    notify_webhook(config, execution)


def execute_paper(
    config: Config,
    signal: ParsedSignal,
    guard: GuardResult,
    run_id: str,
    router_branch: str | None,
) -> PaperExecution:
    execution = build_paper_execution(signal, guard, run_id, router_branch)
    emit_paper_execution(config, execution)
    return execution
