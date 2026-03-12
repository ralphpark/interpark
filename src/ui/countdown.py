import time
from datetime import datetime

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar


class CountdownWidget(QWidget):
    """실시간 카운트다운 표시 위젯."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_timestamp = 0.0
        self.ntp_offset = 0.0
        self.start_remaining = 0.0
        self._blink_on = True
        self._detect_mode = False
        self._click_done = False

        self._setup_ui()

        self.timer = QTimer(self)
        self.timer.setInterval(10)  # 10ms 갱신
        self.timer.timeout.connect(self._update_display)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)

        # 카운트다운 레이블
        self.time_label = QLabel("--:--:--.---")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont("Consolas", 48, QFont.Weight.Bold)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.time_label.setFont(font)
        self.time_label.setStyleSheet("color: #e0e0e0; padding: 10px;")
        layout.addWidget(self.time_label)

        # 상태 텍스트
        self.status_label = QLabel("대기")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #8892b0; font-size: 14px;")
        layout.addWidget(self.status_label)

        # 프로그레스 바
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 10000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #16213e;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e94560, stop:1 #ff6b81);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

    def start(self, target: datetime, ntp_offset: float, detect_mode: bool = False):
        """카운트다운 시작."""
        self.target_timestamp = target.timestamp()
        self.ntp_offset = ntp_offset
        self._detect_mode = detect_mode
        self._click_done = False
        self.start_remaining = self.target_timestamp - (time.time() + ntp_offset)
        if self.start_remaining <= 0:
            self.start_remaining = 1.0
        self.timer.start()

    def on_click_result(self, success: bool):
        """스케줄러에서 실제 클릭 결과를 받았을 때 호출."""
        self._click_done = True
        if success:
            self.time_label.setStyleSheet("color: #2ecc71; padding: 10px;")
            self.progress_bar.setValue(10000)
            self.status_label.setText("클릭 완료!")
        else:
            self.time_label.setStyleSheet("color: #e94560; padding: 10px;")
            self.status_label.setText("클릭 실패")
        # 5초 후 타이머 중지
        QTimer.singleShot(5000, self.timer.stop)

    def stop(self):
        """카운트다운 중지."""
        self.timer.stop()
        self.time_label.setStyleSheet("color: #8892b0; padding: 10px;")
        self.status_label.setText("중지됨")

    def reset(self):
        """초기 상태로 리셋."""
        self.timer.stop()
        self.time_label.setText("--:--:--.---")
        self.time_label.setStyleSheet("color: #e0e0e0; padding: 10px;")
        self.status_label.setText("대기")
        self.progress_bar.setValue(0)
        self._detect_mode = False
        self._click_done = False

    def _update_display(self):
        """10ms 간격으로 카운트다운 갱신."""
        now = time.time() + self.ntp_offset
        remaining = self.target_timestamp - now

        # 진행률 업데이트
        if self.start_remaining > 0:
            elapsed_ratio = 1.0 - (remaining / self.start_remaining)
            progress = max(0, min(10000, int(elapsed_ratio * 10000)))
            self.progress_bar.setValue(progress)

        if remaining > 0:
            # 남은 시간 표시
            total_ms = int(remaining * 1000)
            hours = total_ms // 3600000
            minutes = (total_ms % 3600000) // 60000
            seconds = (total_ms % 60000) // 1000
            ms = total_ms % 1000

            self.time_label.setText(f"-{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}")

            # 색상 변화
            if remaining > 60:
                self.time_label.setStyleSheet("color: #e0e0e0; padding: 10px;")
                self.status_label.setText("대기 중...")
            elif remaining > 10:
                self.time_label.setStyleSheet("color: #f39c12; padding: 10px;")
                self.status_label.setText("곧 시작합니다...")
            else:
                # 10초 이내: 빨간색 깜박임
                self._blink_on = not self._blink_on
                if self._blink_on:
                    self.time_label.setStyleSheet("color: #e94560; padding: 10px;")
                else:
                    self.time_label.setStyleSheet("color: #ff6b81; padding: 10px;")
                self.status_label.setText("준비하세요!")
        else:
            # 시간 초과 후
            elapsed_ms = int(abs(remaining) * 1000)
            hours = elapsed_ms // 3600000
            minutes = (elapsed_ms % 3600000) // 60000
            seconds = (elapsed_ms % 60000) // 1000
            ms = elapsed_ms % 1000

            self.time_label.setText(f"+{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}")

            if self._click_done:
                # 이미 클릭 결과를 받은 상태 - on_click_result에서 처리
                return

            if self._detect_mode:
                # 감지 모드: 클릭 결과 오기 전까지 "감지 중" 표시 (노란색 깜박임)
                self._blink_on = not self._blink_on
                if self._blink_on:
                    self.time_label.setStyleSheet("color: #f39c12; padding: 10px;")
                else:
                    self.time_label.setStyleSheet("color: #e67e22; padding: 10px;")
                self.progress_bar.setValue(10000)
                self.status_label.setText("오픈 감지 중...")

                # 120초 후 타이머 중지
                if abs(remaining) > 120:
                    self.timer.stop()
                    self.status_label.setText("감지 타임아웃")
            else:
                # 정시 모드: 기존 동작 (즉시 클릭 완료 표시)
                self.time_label.setStyleSheet("color: #2ecc71; padding: 10px;")
                self.progress_bar.setValue(10000)
                self.status_label.setText("클릭 완료!")

                # 5초 후 타이머 중지
                if abs(remaining) > 5:
                    self.timer.stop()
