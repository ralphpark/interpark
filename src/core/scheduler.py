import time
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.browser import BrowserManager
from src.core.clicker import TicketClicker


class ClickScheduler(QThread):
    """NTP 동기화 기반 정확한 시간 스케줄링. Chrome CDP 직접 통신."""

    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    click_result_signal = pyqtSignal(bool)

    def __init__(self, target_time: datetime, ntp_offset: float,
                 refresh_enabled: bool = False,
                 url: str = "", debug_port: int = 9222, parent=None):
        super().__init__(parent)
        self.url = url
        self.target_time = target_time
        self.target_timestamp = target_time.timestamp()
        self.ntp_offset = ntp_offset
        self.refresh_enabled = refresh_enabled
        self.debug_port = debug_port
        self.is_running = True
        self._refreshed = False
        self._coords_ready = False

        self.browser = BrowserManager()
        self.clicker = TicketClicker()

    def _now(self) -> float:
        return time.time() + self.ntp_offset

    def _remaining(self) -> float:
        return self.target_timestamp - self._now()

    def run(self):
        try:
            # Phase 1: Chrome CDP 직접 연결
            self.status_signal.emit("Chrome 연결 중...")
            self.log_signal.emit(f"Chrome CDP 직접 연결 (port: {self.debug_port})...")

            if not self.browser.connect(self.debug_port):
                error = self.browser.cdp.last_error if self.browser.cdp else "CDP 초기화 실패"
                self.log_signal.emit(f"Chrome 연결 실패: {error}")
                self.log_signal.emit("Chrome이 실행 중인지 확인하세요")
                self.status_signal.emit("연결 실패")
                self.click_result_signal.emit(False)
                return

            cdp = self.browser.cdp
            self.log_signal.emit("Chrome 연결 성공! (WebSocket 직접)")
            current_url = cdp.get_current_url()
            self.log_signal.emit(f"현재 페이지: {current_url}")

            # Phase 2: 대기 루프
            self.status_signal.emit("대기 중")
            self.log_signal.emit(f"목표 시간: {self.target_time.strftime('%Y-%m-%d %H:%M:%S')}")

            remaining = self._remaining()
            self.log_signal.emit(f"남은 시간: {remaining:.1f}초")

            while self.is_running:
                remaining = self._remaining()

                if remaining <= 0:
                    break

                # 새로고침: 3초 전
                if self.refresh_enabled and remaining <= 3.0 and not self._refreshed:
                    self.status_signal.emit("새로고침 중...")
                    cdp.refresh()
                    self._refreshed = True
                    self.log_signal.emit("페이지 새로고침 완료")
                    time.sleep(0.5)
                    continue

                # 1.5초 전: 버튼 좌표 미리 탐색
                if remaining <= 1.5 and not self._coords_ready:
                    self.status_signal.emit("버튼 탐색 중...")
                    if self.clicker.prefetch_coords(cdp):
                        self._coords_ready = True
                        self.log_signal.emit("버튼 좌표 확보 완료!")
                    else:
                        self.log_signal.emit("버튼 미발견 - 클릭 시 재탐색")

                # 0.3초 전: 스핀락 진입
                if remaining <= 0.3:
                    self.status_signal.emit("클릭 준비!")
                    while self._now() < self.target_timestamp:
                        pass
                    break

                if remaining <= 10.0:
                    time.sleep(0.05)
                else:
                    time.sleep(0.1)

            if not self.is_running:
                self.log_signal.emit("사용자에 의해 중지됨")
                self.status_signal.emit("중지됨")
                return

            # Phase 3: 클릭 실행 (CDP WebSocket 직접)
            click_start = self._now()

            if self._coords_ready:
                success = self.clicker.click_now(cdp)
            else:
                # 좌표 없으면 지금 찾아서 클릭
                if self.clicker.prefetch_coords(cdp):
                    success = self.clicker.click_now(cdp)
                else:
                    success = False

            click_end = self._now()
            diff_ms = (click_start - self.target_timestamp) * 1000
            duration_ms = (click_end - click_start) * 1000

            self.log_signal.emit(f"클릭 시작: 목표 대비 {diff_ms:+.1f}ms")
            self.log_signal.emit(f"클릭 소요: {duration_ms:.1f}ms")

            self.status_signal.emit("클릭 실행!")

            if success:
                self.status_signal.emit("클릭 성공!")
                self.log_signal.emit("예매하기 버튼 클릭 성공!")
            else:
                self.status_signal.emit("버튼 미발견")
                self.log_signal.emit("예매하기 버튼을 찾을 수 없습니다")

            self.click_result_signal.emit(success)

        except Exception as e:
            self.log_signal.emit(f"오류 발생: {str(e)}")
            self.status_signal.emit("오류")
            self.click_result_signal.emit(False)

    def stop(self):
        self.is_running = False

    def cleanup(self):
        self.is_running = False
        self.browser.disconnect()
