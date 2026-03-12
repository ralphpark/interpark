import time
import ntplib


class TimeSync:
    """NTP 서버 기반 시간 동기화."""

    NTP_SERVERS = [
        "time.google.com",
        "time.windows.com",
        "pool.ntp.org",
        "time.nist.gov",
    ]

    def __init__(self):
        self._offset = 0.0
        self._synced = False

    def sync(self) -> float:
        """NTP 서버와 동기화하여 offset 반환. 여러 서버 중 가장 정확한(지연 최소) 값 사용."""
        client = ntplib.NTPClient()
        best_offset = None
        best_delay = float('inf')

        for server in self.NTP_SERVERS:
            try:
                response = client.request(server, version=3, timeout=3)
                # delay가 낮을수록 측정이 정확함
                if response.delay < best_delay:
                    best_delay = response.delay
                    best_offset = response.offset
            except Exception:
                continue

        if best_offset is not None:
            self._offset = best_offset
            self._synced = True
            return self._offset

        self._offset = 0.0
        self._synced = False
        return 0.0

    def get_accurate_time(self) -> float:
        """보정된 현재 시간 (unix timestamp)."""
        return time.time() + self._offset

    def get_offset(self) -> float:
        return self._offset

    def is_synced(self) -> bool:
        return self._synced
