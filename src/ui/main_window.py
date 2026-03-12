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
from src.core.browser import BrowserManager, find_chrome_path, CDPConnection
from src.core.clicker import TicketClicker
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
        self.setMinimumSize(560, 780)
        self.resize(560, 780)
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
        guide_label = QLabel(
            "Chrome이 열리면 인터파크 로그인 → 티켓 페이지 → "
            "일시와 '일반예매'라고 적힌 회색 버튼이 보이는 페이지까지 이동하세요"
        )
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

        self.btn_auto_time = QPushButton("일시 자동인식")
        self.btn_auto_time.setFixedHeight(36)
        self.btn_auto_time.setToolTip("Chrome 페이지의 버튼에서 오픈 일시를 자동으로 읽어옵니다")
        self.btn_auto_time.clicked.connect(self._on_auto_time_clicked)
        dt_layout.addWidget(self.btn_auto_time)

        layout.addLayout(dt_layout)

        # 자동인식 결과 표시
        self.auto_time_label = QLabel("")
        self.auto_time_label.setStyleSheet("color: #2ecc71; font-size: 11px;")
        layout.addWidget(self.auto_time_label)

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
        self._add_log("   - '일반예매' 회색 버튼이 보이는 페이지까지")
        self._add_log("3. '일시 자동인식' 클릭 → 오픈 시간 자동 설정")
        self._add_log("4. '대기 시작' 클릭 → 오픈 감지 + 즉시 클릭!")
        self._add_log("")
        self._add_log("회색 버튼이 파란색 '예매하기'로 바뀌는 순간")
        self._add_log("자동으로 감지하여 최고속으로 클릭합니다!")
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
            self._add_log("이 Chrome 창에서 인터파크 로그인 → 티켓 페이지 → 회색 버튼 페이지까지 이동하세요")
            self._add_log("(기존 Chrome과 별도 창이므로 로그인이 필요합니다)")
            # Chrome 연결 상태 주기적 확인
            if not hasattr(self, '_heartbeat_timer'):
                from PyQt6.QtCore import QTimer as QT
                self._heartbeat_timer = QT(self)
                self._heartbeat_timer.setInterval(30000)  # 30초
                self._heartbeat_timer.timeout.connect(self._check_chrome_alive)
                self._heartbeat_timer.start()
        else:
            self._add_log("[ERROR] Chrome 실행 실패")
            self._add_log("이미 Chrome이 실행 중이면 모두 닫고 다시 시도하세요")

        self.btn_launch_chrome.setEnabled(True)

    def _on_auto_time_clicked(self):
        """Chrome 페이지에서 버튼 텍스트를 읽어 오픈 일시 자동 설정."""
        if not self._chrome_launched:
            self._add_log("[자동인식] Chrome이 실행되지 않았습니다. 먼저 Chrome을 실행하세요.")
            self.auto_time_label.setText("Chrome 미실행")
            self.auto_time_label.setStyleSheet("color: #e94560; font-size: 11px;")
            return

        self._add_log("[자동인식] 버튼에서 오픈 시간 읽는 중...")
        try:
            cdp = CDPConnection(self.DEBUG_PORT)
            if not cdp.connect():
                self._add_log("[자동인식] Chrome 연결 실패 - 수동으로 시간을 설정하세요")
                self.auto_time_label.setText("Chrome 연결 실패")
                self.auto_time_label.setStyleSheet("color: #e94560; font-size: 11px;")
                cdp.close()
                return

            clicker = TicketClicker()

            # 버튼 상태 확인 + 로그
            state = clicker.check_button_state(cdp)
            if state:
                state_type = state.get('state', 'unknown')
                color = state.get('color', '')
                text = state.get('text', '')
                self._add_log(f"[자동인식] 버튼 상태: {state_type} | 텍스트: [{text}] | 색상: {color}")

                if state_type == 'open':
                    self._add_log("[자동인식] 이미 오픈(파란색) 상태입니다!")
                    self.auto_time_label.setText("이미 오픈 상태 - 바로 대기 시작하세요")
                    self.auto_time_label.setStyleSheet("color: #f39c12; font-size: 11px;")
            else:
                self._add_log("[자동인식] 버튼을 찾을 수 없습니다")

            # 시간 파싱 시도
            time_info = clicker.parse_button_time(cdp)
            if time_info:
                month = time_info['month']
                day = time_info['day']
                hour = time_info['hour']
                minute = time_info['minute']
                btn_text = time_info['text']
                source = time_info.get('source', 'button')

                # year가 직접 제공된 경우 (티켓오픈안내 영역)
                if 'year' in time_info:
                    year = time_info['year']
                else:
                    now = datetime.now()
                    year = now.year
                    if month < now.month:
                        year += 1

                self.date_edit.setDate(QDate(year, month, day))
                self.time_edit.setTime(QTime(hour, minute, 0))

                result_text = f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:00"
                source_label = {'ticket_open_info': '티켓오픈안내', 'page_text': '페이지 텍스트', 'button': '버튼'}.get(source, source)
                self._add_log(f"[자동인식] 오픈 시간 설정 완료: {result_text} (출처: {source_label})")
                self._add_log(f"[자동인식] 원문: [{btn_text}]")
                self.auto_time_label.setText(f"자동 인식 완료: {result_text}")
                self.auto_time_label.setStyleSheet("color: #2ecc71; font-size: 11px;")
            else:
                self._add_log("[자동인식] 버튼에서 시간 정보를 찾지 못했습니다")
                self._add_log("[자동인식] 수동으로 시간을 설정하세요")
                self.auto_time_label.setText("시간 인식 실패 - 수동 설정하세요")
                self.auto_time_label.setStyleSheet("color: #e94560; font-size: 11px;")

            cdp.close()
        except Exception as e:
            self._add_log(f"[자동인식] 오류: {str(e)}")
            self.auto_time_label.setText("오류 발생")
            self.auto_time_label.setStyleSheet("color: #e94560; font-size: 11px;")

    def _on_start_clicked(self):
        if not self._chrome_launched:
            self._add_log("[ERROR] 먼저 'Chrome 실행' 버튼을 눌러주세요")
            return

        # 자동 시간 동기화
        self._add_log("NTP 시간 동기화 중...")
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

        # 과거 시간 → 내일로 자동 보정
        now = datetime.now() + timedelta(seconds=self.time_sync.get_offset())
        if target <= now:
            target += timedelta(days=1)
            self.date_edit.setDate(QDate(target.year, target.month, target.day))
            self._add_log(f"[알림] 과거 시간 → 내일로 자동 보정: {target.strftime('%Y-%m-%d %H:%M:%S')}")

        # 10시간 이내 체크
        diff_hours = (target - now).total_seconds() / 3600
        if diff_hours > 10:
            self._add_log(f"[ERROR] 대기 가능 시간은 최대 10시간입니다 (현재: {diff_hours:.1f}시간)")
            return

        # UI 상태 전환
        self._set_controls_enabled(False)

        # 카운트다운 시작 (항상 감지 모드)
        self.countdown_widget.start(target, self.time_sync.get_offset(), detect_mode=True)

        # 스케줄러 시작 (항상 감지 모드)
        self.scheduler = ClickScheduler(
            target_time=target,
            ntp_offset=self.time_sync.get_offset(),
            debug_port=self.DEBUG_PORT,
        )
        self.scheduler.log_signal.connect(self._add_log)
        self.scheduler.status_signal.connect(self._update_status)
        self.scheduler.click_result_signal.connect(self._on_click_result)
        self.scheduler.finished.connect(self._on_scheduler_finished)
        self.scheduler.start()

        self._add_log("=== 대기 시작 ===")
        self._add_log(f"목표 시간: {target.strftime('%Y-%m-%d %H:%M:%S')}")
        self._add_log(f"남은 시간: {diff_hours:.1f}시간 ({(target - now).total_seconds():.0f}초)")
        self._add_log("모드: 오픈 감지 → 즉시 클릭")
        self._add_log(f"감지 시작: 목표 30초 전부터 50ms 간격 폴링")

    def _on_stop_clicked(self):
        if self.scheduler:
            self.scheduler.stop()
        self.countdown_widget.stop()
        self._add_log("=== 사용자 중지 ===")
        self._set_controls_enabled(True)

    def _on_click_result(self, success: bool):
        # 카운트다운 위젯에 실제 클릭 결과 전달
        self.countdown_widget.on_click_result(success)
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
        self.btn_auto_time.setEnabled(enabled)

    MAX_LOG_LINES = 500

    def _add_log(self, message: str):
        formatted = self.logger.log(message)
        self.log_panel.append(formatted)
        # 로그 500줄 제한
        doc = self.log_panel.document()
        if doc.blockCount() > self.MAX_LOG_LINES:
            cursor = self.log_panel.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor,
                              doc.blockCount() - self.MAX_LOG_LINES)
            cursor.removeSelectedText()
            cursor.deleteChar()  # remove leftover newline
        scrollbar = self.log_panel.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_status(self, status: str):
        self.state_label.setText(f"Status: {status}")

    def _check_chrome_alive(self):
        """Chrome 연결 상태 주기적 확인."""
        if not self._chrome_launched:
            return
        try:
            import urllib.request
            import json
            resp = urllib.request.urlopen(
                f'http://127.0.0.1:{self.DEBUG_PORT}/json',
                timeout=2,
            )
            targets = json.loads(resp.read())
            pages = [t for t in targets if t.get('type') == 'page']
            if pages:
                self.chrome_status.setText(f"Chrome 연결됨 ({len(pages)}탭)")
                self.chrome_status.setStyleSheet("color: #2ecc71; font-size: 13px; font-weight: bold;")
                return
        except Exception:
            pass
        self.chrome_status.setText("Chrome 연결 끊김!")
        self.chrome_status.setStyleSheet("color: #e94560; font-size: 13px; font-weight: bold;")

    def closeEvent(self, event):
        if hasattr(self, '_heartbeat_timer'):
            self._heartbeat_timer.stop()
        if self.scheduler:
            self.scheduler.cleanup()
        event.accept()
