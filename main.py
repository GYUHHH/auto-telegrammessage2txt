import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


API_BASE = "https://api.telegram.org/bot{token}/{method}"


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def telegram_api(token: str, method: str, data=None, files=None):
    url = API_BASE.format(token=token, method=method)
    response = requests.post(url, data=data, files=files, timeout=30)
    try:
        payload = response.json()
    except Exception:
        raise RuntimeError(f"Telegram API returned non-JSON response: {response.text[:500]}")

    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error on {method}: {payload}")
    return payload["result"]


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"last_update_id": 0}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_all_updates(token: str, offset: int | None) -> list[dict]:
    """Drain pending updates in chunks of max 100."""
    updates: list[dict] = []
    current_offset = offset

    for _ in range(20):  # safety limit: max 2000 updates/run
        data = {
            "limit": 100,
            "timeout": 0,
            "allowed_updates": json.dumps(["message", "edited_message"]),
        }
        if current_offset is not None and current_offset > 0:
            data["offset"] = current_offset

        batch = telegram_api(token, "getUpdates", data=data)
        if not batch:
            break

        updates.extend(batch)
        current_offset = max(item["update_id"] for item in batch) + 1

        if len(batch) < 100:
            break

    return updates


def message_text(message: dict) -> str:
    if "text" in message:
        return message["text"]
    if "caption" in message:
        return message["caption"]

    known_types = [
        "photo", "video", "voice", "audio", "document", "sticker",
        "animation", "video_note", "location", "contact", "poll"
    ]
    found = [kind for kind in known_types if kind in message]
    if found:
        return f"[{', '.join(found)}]"
    return "[non-text message]"


def sender_name(message: dict) -> str:
    user = message.get("from", {})
    name = " ".join(
        part for part in [user.get("first_name"), user.get("last_name")] if part
    ).strip()
    username = user.get("username")
    if username:
        return f"{name} (@{username})" if name else f"@{username}"
    return name or "Unknown"


def build_markdown(messages: list[dict], start_dt: datetime, end_dt: datetime, tz_name: str) -> str:
    title = f"{start_dt.strftime('%Y-%m-%d %H:%M')} ~ {end_dt.strftime('%Y-%m-%d %H:%M')}"
    lines = [
        f"# Telegram Daily Export",
        "",
        f"- Range: `{title}`",
        f"- Timezone: `{tz_name}`",
        f"- Messages: `{len(messages)}`",
        "",
        "## Messages",
        "",
    ]

    if not messages:
        lines.append("_No messages collected for this range._")
        return "\n".join(lines)

    for item in messages:
        dt = item["local_dt"]
        lines.append(f"### {dt.strftime('%Y-%m-%d %H:%M')} - {item['sender']}")
        lines.append("")
        lines.append(item["text"].strip() or "[empty]")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    token = required_env("TELEGRAM_BOT_TOKEN")
    report_chat_id = required_env("REPORT_CHAT_ID")
    group_chat_id = os.getenv("GROUP_CHAT_ID", "").strip()
    tz_name = os.getenv("TIMEZONE", "Asia/Seoul")
    tz = ZoneInfo(tz_name)

    # 한국시간 오전 3시에 실행되면, 직전 24시간 기록을 보냅니다.
    # 예: 5/27 03:00 실행 → 5/26 03:00 ~ 5/27 03:00 기록
    window_hours = int(os.getenv("WINDOW_HOURS", "24"))

    state_path = Path(os.getenv("STATE_FILE", "state.json"))
    output_dir = Path(os.getenv("OUTPUT_DIR", "logs"))
    output_dir.mkdir(parents=True, exist_ok=True)

    state = load_state(state_path)
    last_update_id = int(state.get("last_update_id", 0))
    offset = last_update_id + 1 if last_update_id > 0 else None

    updates = get_all_updates(token, offset=offset)
    max_update_id = last_update_id

    now = datetime.now(tz)
    end_dt = now
    start_dt = end_dt - timedelta(hours=window_hours)

    collected = []

    for update in updates:
        update_id = int(update["update_id"])
        max_update_id = max(max_update_id, update_id)

        message = update.get("message") or update.get("edited_message")
        if not message:
            continue

        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        if group_chat_id and chat_id != group_chat_id:
            continue

        unix_ts = message.get("date")
        if not unix_ts:
            continue

        local_dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc).astimezone(tz)

        if not (start_dt <= local_dt < end_dt):
            continue

        collected.append({
            "local_dt": local_dt,
            "sender": sender_name(message),
            "text": message_text(message),
        })

    collected.sort(key=lambda x: x["local_dt"])

    filename_time = end_dt.strftime("%Y-%m-%d-0300")
    report_path = output_dir / f"telegram-{filename_time}.md"
    report_path.write_text(build_markdown(collected, start_dt, end_dt, tz_name), encoding="utf-8")

    caption = (
        f"Telegram export\n"
        f"{start_dt.strftime('%Y-%m-%d %H:%M')} ~ {end_dt.strftime('%Y-%m-%d %H:%M')}\n"
        f"{len(collected)} messages"
    )

    if collected:
        with report_path.open("rb") as f:
            telegram_api(
                token,
                "sendDocument",
                data={"chat_id": report_chat_id, "caption": caption},
                files={"document": (report_path.name, f, "text/markdown")},
            )
    else:
        telegram_api(
            token,
            "sendMessage",
            data={
                "chat_id": report_chat_id,
                "text": caption + "\n수집된 메시지가 없습니다.",
            },
        )

    # Save offset only after Telegram delivery succeeds.
    state["last_update_id"] = max_update_id
    state["last_run_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state_path, state)

    print(f"Delivered {len(collected)} messages from {start_dt} to {end_dt}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
