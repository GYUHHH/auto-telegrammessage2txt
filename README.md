# Telegram Daily Exporter - 3AM KST Version

텔레그램 그룹방에 추가한 봇이 **한국시간 오전 3시**에 직전 기록을 모아서 내 텔레그램 DM으로 `.md` 파일을 보내는 개인용 자동화입니다.

## 실행 기준

기본 설정은 다음과 같습니다.

```text
매일 한국시간 03:00 실행
직전 24시간 기록 수집
예: 5월 27일 03:00 실행 → 5월 26일 03:00 ~ 5월 27일 03:00 기록 전송
```

이렇게 한 이유는 오전 3시에 실행할 때 `오늘 날짜`만 기준으로 잡으면 00:00~03:00 기록만 잡힐 수 있기 때문입니다.

## 수정된 핵심

### 1. GitHub Actions 실행 시간

`.github/workflows/daily_telegram_export.yml`

```yaml
schedule:
  # 03:00 KST = 18:00 UTC
  - cron: "0 18 * * *"
```

GitHub Actions cron은 UTC 기준입니다.

```text
한국시간 03:00 = 전날 UTC 18:00
```

### 2. 수집 범위

`main.py`

```python
window_hours = int(os.getenv("WINDOW_HOURS", "24"))
end_dt = now
start_dt = end_dt - timedelta(hours=window_hours)
```

즉, 실행 시점 기준 직전 24시간을 가져옵니다.

## 1. 봇 만들기

Telegram에서 `@BotFather`에게 다음 명령을 보냅니다.

```text
/newbot
```

봇 이름과 username을 정하면 `TELEGRAM_BOT_TOKEN`을 줍니다.

## 2. 봇을 그룹에 추가

기존 그룹방에서:

```text
그룹 정보 → Add Members → 봇 검색 → 추가
```

그룹 전체 메시지를 받으려면 BotFather에서 privacy mode를 끕니다.

```text
/mybots → 내 봇 → Bot Settings → Group Privacy → Turn off
```

## 3. 내 DM chat_id와 그룹 chat_id 확인

1. 만든 봇에게 개인 DM으로 `/start`를 보냅니다.
2. 그룹방에 아무 메시지나 보냅니다.
3. 브라우저에서 아래 주소를 엽니다.

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates
```

응답에서:

```text
내 개인 DM의 chat.id → REPORT_CHAT_ID
그룹방의 chat.id → GROUP_CHAT_ID
```

그룹방 ID는 보통 `-100...` 형태입니다.

## 4. GitHub Repository에 업로드

1. GitHub에서 새 repository를 만듭니다.
2. 이 폴더의 파일을 그대로 올립니다.
3. 가능하면 private repo를 권장합니다.

## 5. GitHub Secrets 설정

Repository에서:

```text
Settings → Secrets and variables → Actions → New repository secret
```

아래 3개를 추가합니다.

```text
TELEGRAM_BOT_TOKEN = BotFather가 준 토큰
REPORT_CHAT_ID = 내 개인 DM chat.id
GROUP_CHAT_ID = 그룹방 chat.id
```

## 6. Actions 권한 설정

Repository에서:

```text
Settings → Actions → General
```

아래 옵션을 켭니다.

```text
Workflow permissions → Read and write permissions
```

이 권한이 있어야 `state.json`을 자동 커밋할 수 있습니다.

## 7. 수동 테스트

GitHub repository에서:

```text
Actions → Daily Telegram Export → Run workflow
```

실행 후 내 텔레그램 DM으로 파일이 오면 성공입니다.

## 주의

- 봇을 넣은 이후의 메시지만 수집됩니다.
- 봇이 그룹 전체 메시지를 받으려면 Group Privacy를 OFF 해야 합니다.
- 이 버전은 AI 요약 없이 원문 추출만 합니다.
- 메시지 원문은 repository에 커밋하지 않고, 텔레그램 DM으로만 보냅니다.
