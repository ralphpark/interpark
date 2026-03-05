from datetime import datetime


class AppLogger:
    """타임스탬프 포함 로그 관리."""

    @staticmethod
    def log(message: str) -> str:
        now = datetime.now()
        ts = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"
        return f"[{ts}] {message}"

    @staticmethod
    def log_with_level(level: str, message: str) -> str:
        now = datetime.now()
        ts = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"
        return f"[{ts}] [{level}] {message}"
