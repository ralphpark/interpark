from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QDate, QTime
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QDateEdit, QTimeEdit, QFrame, QStatusBar,
)

from src.ui.countdown import CountdownWidget
from src.ui.styles import DARK_THEME
from src.core.browser import BrowserManager, find_chrome_path
from src.core.scheduler import ClickScheduler
from src.utils.time_sync import TimeSync
from src.utils.logger import AppLogger


class MainWindow(QMainWindow):
    """메인 윈도우. 모든 UI 위젯 통합."""

    DEBUG_PORT = 9222

    def __init__(self):
        super().__init__()
        self.scheduler = None
        self.time_sync = TimeSync()
        self.logger = AppLogger()
        self._browser_mgr = BrowserManager()
        self._chrome_launched = False

        self.setWindowTitle("🥑 아보카도 티켓 매크로")
        self.setFixedSize(560, 780)
        self.setStyleSheet(DARK_THEME)

        self._setup_ui()
        self._show_guide()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 16, 24, 8)
        layout.setSpacing(6)

        # ── Title ──
        title = QLabel("🥑 아보카도 티켓 매크로")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addWidget(self._separator())

        # ── Step 1: Chrome 실행 ──
        layout.addWidget(self._section_label("STEP 1. Chrome 실행"))

        chrome_layout = QHBoxLayout()
        chrome_layout.setSpacing(10)

        self.btn_launch_chrome = QPushButton("Chrome 실행")
        self.btn_launch_chrome.setObjectName("startBtn")
        self.btn_launch_chrome.setFixedHeight(40)
        self.btn_launch_chrome.clicked.connect(self._on_launch_chrome)
        chrome_layout.addWidget(self.btn_launch_chrome)

        self.chrome_status = QLabel("Chrome 미실행")
        self.chrome_status.setStyleSheet("color: #e94560; font-size: 13px; font-weight: bold;")
        chrome_layout.addWidget(self.chrome_status)
        chrome_layout.addStretch()

        layout.addLayout(chrome_layout)

        # 안내 문구
        guide_label = QLabel("Chrome이 열리면 인터파크 로그인 → 티켓 페이지 → 회차 선택까지 완료하세요")
        guide_label.setStyleSheet("color: #8892b0; font-size: 11px;")
        guide_label.setWordWrap(True)
        layout.addWidget(guide_label)

        layout.addWidget(self._separator())

        # ── Step 2: 목표 시간 ──
        layout.addWidget(self._section_label("STEP 2. 목표 시간 설정"))
        dt_layout = QHBoxLayout()
        dt_layout.setSpacing(10)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setFont(QFont("Consolas", 12))
        dt_layout.addWidget(self.date_edit, stretch=1)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm:ss")
        now = QTime.currentTime()
        self.time_edit.setTime(QTime(now.hour(), now.minute(), 0))
        self.time_edit.setFont(QFont("Consolas", 12))
        dt_layout.addWidget(self.time_edit, stretch=1)

        layout.addLayout(dt_layout)

        layout.addWidget(self._separator())

        # ── Countdown ──
        self.countdown_widget = CountdownWidget()
        layout.addWidget(self.countdown_widget)

        layout.addWidget(self._separator())

        # ── Step 3: 실행 ──
        layout.addWidget(self._section_label("STEP 3. 실행"))
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_start = QPushButton("대기 시작")
        self.btn_start.setObjectName("startBtn")
        self.btn_start.setFixedHeight(42)
        self.btn_start.clicked.connect(self._on_start_clicked)
        btn_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("중지")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setFixedHeight(42)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        btn_layout.addWidget(self.btn_stop)

        layout.addLayout(btn_layout)

        # ── Log Panel ──
        layout.addWidget(self._section_label("LOG"))
        self.log_panel = QTextEdit()
        self.log_panel.setObjectName("logPanel")
        self.log_panel.setReadOnly(True)
        self.log_panel.setFont(QFont("Consolas", 11))
        self.log_panel.setMinimumHeight(150)
        layout.addWidget(self.log_panel)

        # ── Status Bar ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.ntp_label = QLabel("시간: 대기 시작 시 자동 동기화")
        self.state_label = QLabel("Status: 대기")
        self.status_bar.addWidget(self.ntp_label, stretch=1)
        self.status_bar.addPermanentWidget(self.state_label)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setObjectName("separator")
        line.setFrameShape(QFrame.Shape.HLine)
        return line

    def _show_guide(self):
        """시작 시 사용 가이드 출력."""
        self._add_log("=== 🥑 사용 방법 ===")
        self._add_log("")
        self._add_log("1. 'Chrome 실행' 버튼 클릭")
        self._add_log("2. 열린 Chrome에서:")
        self._add_log("   - 인터파크 로그인")
        self._add_log("   - 원하는 티켓 페이지로 이동")
        self._add_log("   - 회차 선택")
        self._add_log("3. 목표 시간 설정 → '대기 시작'")
        self._add_log("")
        self._add_log("정확한 시간에 자동으로 '예매하기'를 클릭합니다!")
        self._add_log("=========================================")

    # ── Slots ──

    def _on_launch_chrome(self):
        """Chrome을 디버깅 모드로 실행."""
        chrome_path = find_chrome_path()
        if not chrome_path:
            self._add_log("[ERROR] Chrome을 찾을 수 없습니다")
            self._add_log("Google Chrome이 설치되어 있는지 확인하세요")
            return

        self._add_log("Chrome 실행 중...")
        self.btn_launch_chrome.setEnabled(False)

        result = self._browser_mgr.launch_chrome_debug(self.DEBUG_PORT)

        if result:
            self._chrome_launched = True
            self.chrome_status.setText("Chrome 실행됨")
            self.chrome_status.setStyleSheet("color: #2ecc71; font-size: 13px; font-weight: bold;")
            self._add_log("Chrome 실행 완료! (매크로 전용 창)")
            self._add_log("이 Chrome 창에서 인터파크 로그인 + 티켓 페이지 + 회차 선택을 완료하세요")
            self._add_log("(기존 Chrome과 별도 창이므로 로그인이 필요합니다)")
        else:
            self._add_log("[ERROR] Chrome 실행 실패")
            self._add_log("이미 Chrome이 실행 중이면 모두 닫고 다시 시도하세요")

        self.btn_launch_chrome.setEnabled(True)

    def _on_start_clicked(self):
        if not self._chrome_launched:
            self._add_log("[ERROR] 먼저 'Chrome 실행' 버튼을 눌러주세요")
            return

        # 자동 시간 동기화
        self._add_log("시간 동기화 중...")
        offset = self.time_sync.sync()
        if self.time_sync.is_synced():
            self.ntp_label.setText(f"시간 보정: {offset:+.3f}s")
            self._add_log(f"시간 동기화 완료! (보정값: {offset:+.4f}초)")
        else:
            self.ntp_label.setText("시간: 로컬 시간 사용")
            self._add_log("시간 동기화 실패 - 로컬 시간을 사용합니다")

        # 날짜가 과거이면 오늘로 자동 보정
        today = QDate.currentDate()
        if self.date_edit.date() < today:
            self.date_edit.setDate(today)

        # 목표 시간 구성
        qdate = self.date_edit.date()
        qtime = self.time_edit.time()
        target = datetime(
            qdate.year(), qdate.month(), qdate.day(),
            qtime.hour(), qtime.minute(), qtime.second()
        )

        # 과거 시간 체크
        now = datetime.now() + timedelta(seconds=self.time_sync.get_offset())
        if target <= now:
            self._add_log("[ERROR] 목표 시간이 현재보다 과거입니다")
            return

        # UI 상태 전환
        self._set_controls_enabled(False)

        # 카운트다운 시작
        self.countdown_widget.start(target, self.time_sync.get_offset())

        # 스케줄러 시작
        self.scheduler = ClickScheduler(
            target_time=target,
            ntp_offset=self.time_sync.get_offset(),
            refresh_enabled=False,
            debug_port=self.DEBUG_PORT,
        )
        self.scheduler.log_signal.connect(self._add_log)
        self.scheduler.status_signal.connect(self._update_status)
        self.scheduler.click_result_signal.connect(self._on_click_result)
        self.scheduler.finished.connect(self._on_scheduler_finished)
        self.scheduler.start()

        self._add_log("=== 대기 시작 ===")
        self._add_log(f"목표: {target.strftime('%Y-%m-%d %H:%M:%S')}")
        self._add_log("새로고침: OFF")

    def _on_stop_clicked(self):
        if self.scheduler:
            self.scheduler.stop()
        self.countdown_widget.stop()
        self._add_log("=== 사용자 중지 ===")
        self._set_controls_enabled(True)

    def _on_click_result(self, success: bool):
        if success:
            self._add_log(">>> 예매하기 클릭 성공! 브라우저에서 확인하세요 <<<")
        else:
            self._add_log(">>> 예매하기 버튼을 찾지 못했습니다 <<<")

    def _on_scheduler_finished(self):
        self._set_controls_enabled(True)

    def _set_controls_enabled(self, enabled: bool):
        self.btn_start.setEnabled(enabled)
        self.btn_stop.setEnabled(not enabled)
        self.date_edit.setEnabled(enabled)
        self.time_edit.setEnabled(enabled)

    def _add_log(self, message: str):
        formatted = self.logger.log(message)
        self.log_panel.append(formatted)
        scrollbar = self.log_panel.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_status(self, status: str):
        self.state_label.setText(f"Status: {status}")

    def closeEvent(self, event):
        if self.scheduler:
            self.scheduler.cleanup()
        event.accept()
