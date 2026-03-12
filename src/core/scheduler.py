import time
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.browser import BrowserManager
from src.core.clicker import TicketClicker


class ClickScheduler(QThread):
    """오픈 감지 + 즉시 클릭 스케줄러. Chrome CDP 직접 통신."""

    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    click_result_signal = pyqtSignal(bool)

    # 감지 시작: 목표 30초 전
    DETECT_START_SECONDS = 30
    # 감지 폴링 간격: 30ms (1초에 33회) - 더 빠른 폴백 감지
    DETECT_POLL_MS = 30
    # 감지 타임아웃: 목표 시간 + 120초
    DETECT_TIMEOUT_SECONDS = 120

    def __init__(self, target_time: datetime, ntp_offset: float,
                 debug_port: int = 9222, parent=None):
        super().__init__(parent)
        self.target_time = target_time
        self.target_timestamp = target_time.timestamp()
        self.ntp_offset = ntp_offset
        self.debug_port = debug_port
        self.is_running = True

        self.browser = BrowserManager()
        self.clicker = TicketClicker()

    def _now(self) -> float:
        return time.time() + self.ntp_offset

    def _remaining(self) -> float:
        return self.target_timestamp - self._now()

    def run(self):
        try:
            # ── Phase 1: Chrome 연결 ──
            self.status_signal.emit("Chrome 연결 중...")
            self.log_signal.emit(f"[연결] Chrome CDP 직접 연결 (port: {self.debug_port})...")

            if not self.browser.connect(self.debug_port):
                error = self.browser.cdp.last_error if self.browser.cdp else "CDP 초기화 실패"
                self.log_signal.emit(f"[연결] 실패: {error}")
                self.log_signal.emit("[연결] Chrome이 실행 중인지 확인하세요")
                self.status_signal.emit("연결 실패")
                self.click_result_signal.emit(False)
                return

            cdp = self.browser.cdp
            self.log_signal.emit("[연결] Chrome 연결 성공! (WebSocket)")
            current_url = cdp.get_current_url()
            self.log_signal.emit(f"[연결] 현재 페이지: {current_url}")

            # 현재 버튼 상태 확인
            state = self.clicker.check_button_state(cdp)
            if state:
                s = state.get('state', 'unknown')
                t = state.get('text', '')
                c = state.get('color', '')
                self.log_signal.emit(f"[상태] 버튼: {s} | 텍스트: [{t}] | 색상: {c}")
            else:
                self.log_signal.emit("[상태] 버튼을 찾을 수 없습니다")

            # ── Phase 2: 대기 ──
            remaining = self._remaining()
            self.log_signal.emit(f"[대기] 목표 시간: {self.target_time.strftime('%Y-%m-%d %H:%M:%S')}")
            self.log_signal.emit(f"[대기] 남은 시간: {remaining:.1f}초 ({remaining/3600:.1f}시간)")
            self.log_signal.emit(f"[대기] 감지 시작: 목표 {self.DETECT_START_SECONDS}초 전")

            last_log_remaining = remaining
            detect_started = False
            poll_count = 0
            initially_open = False
            auto_click_installed = False

            while self.is_running:
                remaining = self._remaining()

                # ── Phase 3: 감지 시작 ──
                if remaining <= self.DETECT_START_SECONDS and not detect_started:
                    detect_started = True
                    self.log_signal.emit(f"[감지] === 감지 시작! (남은 시간: {remaining:.1f}초) ===")

                    state = self.clicker.check_button_state(cdp)
                    if state and state.get('state') == 'open':
                        if remaining <= 0:
                            self.log_signal.emit("[감지] 이미 오픈 상태! 즉시 클릭!")
                            self._do_click(cdp, state)
                            return
                        else:
                            initially_open = True
                            self.log_signal.emit(f"[감지] 이미 오픈 상태 - 목표 시간({self.target_time.strftime('%H:%M:%S')})까지 대기")
                            self.clicker.prefetch_coords(cdp)
                    else:
                        if state and state.get('state') == 'pending':
                            t = state.get('text', '')
                            cd = state.get('countdown', '')
                            if state.get('type') == 'countdown':
                                self.log_signal.emit(f"[감지] 카운트다운: [{t}] 남은: {cd}")
                            elif state.get('reason') == 'page_not_ready':
                                self.log_signal.emit(f"[감지] 예매하기 버튼 있으나 달력/회차 미로드 → 대기")
                            else:
                                self.log_signal.emit(f"[감지] 오픈 예정: [{t}]")

                        # ★ 핵심: 브라우저 내부 고속 자동클릭 설치 (10ms setInterval)
                        # "예매하기" 버튼 등장 즉시 JS에서 클릭 → CDP 왕복 0ms
                        auto_result = self.clicker.inject_auto_click(cdp)
                        if auto_result and auto_result.get('status') == 'installed':
                            auto_click_installed = True
                            self.log_signal.emit(f"[감지] ★ 브라우저 내부 자동클릭 설치! (5ms + Observer)")
                            self.log_signal.emit("[감지] 달력+회차 로딩 후 예매하기 버튼 즉시 클릭")
                        self.log_signal.emit("[감지] 버튼 변화 대기 중...")

                # ── 감지 폴링 루프 ──
                if detect_started:
                    poll_count += 1

                    # ★ 통합 체크: 자동클릭 결과 + 버튼 상태를 1회 CDP 호출로 확인
                    combined = self.clicker.combined_check(cdp)

                    # ── 자동클릭 성공 체크 ──
                    if combined and combined.get('autoClicked'):
                        self._handle_auto_click_success(cdp, combined['autoClicked'], poll_count)
                        return

                    # ── 자동클릭 생존 확인 + 재설치 (매 10회 = ~300ms마다) ──
                    if auto_click_installed and poll_count % 10 == 0:
                        if combined and not combined.get('autoClickActive'):
                            # 타이머 죽음 = 페이지 리로드됨 → 재설치!
                            re_result = self.clicker.inject_auto_click(cdp)
                            if re_result and re_result.get('status') == 'installed':
                                self.log_signal.emit("[감지] ★ 자동클릭 재설치! (페이지 리로드 감지)")

                    # ── 버튼 상태 처리 ──
                    state = combined.get('buttonState') if combined else None

                    if state and state.get('state') == 'open':
                        if initially_open and remaining > 0:
                            # 이미 오픈 + 목표 시간 전 → 대기
                            if remaining <= 1.0:
                                self.clicker.prefetch_coords(cdp)
                            if poll_count % 33 == 0:
                                self.status_signal.emit(f"대기 중... (오픈, {remaining:.1f}초 후 클릭)")
                            time.sleep(self.DETECT_POLL_MS / 1000.0)
                            continue

                        # 전환 감지 or 목표 시간 도달 → 즉시 클릭 (폴백)
                        detect_time = self._now()
                        diff_ms = (detect_time - self.target_timestamp) * 1000
                        if initially_open:
                            self.log_signal.emit(f"[감지] 목표 시간 도달! 클릭!")
                        else:
                            self.log_signal.emit(f"[감지] 오픈 감지! (폴링 {poll_count}회, {diff_ms:+.1f}ms)")
                        self._do_click(cdp, state)
                        return

                    # 상태 변화 감지
                    if initially_open and state and state.get('state') != 'open':
                        initially_open = False
                        self.log_signal.emit("[감지] 버튼 상태 변경 → 전환 감지 모드")
                        self.clicker.cleanup_auto_click(cdp)
                        auto_result = self.clicker.inject_auto_click(cdp)
                        if auto_result and auto_result.get('status') == 'installed':
                            auto_click_installed = True

                    # unknown 시 자동클릭 재설치
                    if not state or state.get('state') == 'unknown':
                        uc = getattr(self, '_uc', 0) + 1
                        self._uc = uc
                        if uc % 10 == 0:
                            self.log_signal.emit(f"[감지] 버튼 미발견 {uc}회 - 재탐색...")
                            self.clicker.cleanup_auto_click(cdp)
                            auto_result = self.clicker.inject_auto_click(cdp)
                            if auto_result and auto_result.get('status') == 'installed':
                                auto_click_installed = True
                    else:
                        self._uc = 0

                    # 상태 로그 (1초마다 = ~33회)
                    if poll_count % 33 == 0:
                        elapsed = poll_count * self.DETECT_POLL_MS / 1000
                        s = state.get('state', '?') if state else '없음'
                        reason = state.get('reason', '') if state else ''
                        ac = '활성' if auto_click_installed else '미설치'
                        extra = ' (달력/회차 대기)' if reason == 'page_not_ready' else ''
                        self.status_signal.emit(f"감지 중... ({poll_count}회, {remaining:.1f}초){extra}")
                        self.log_signal.emit(
                            f"[감지] {poll_count}회 | {s}{extra} | 자동클릭: {ac} | {remaining:.1f}초"
                        )

                    time.sleep(self.DETECT_POLL_MS / 1000.0)

                    # 타임아웃
                    if remaining < -self.DETECT_TIMEOUT_SECONDS:
                        self.log_signal.emit(f"[감지] 타임아웃! ({poll_count}회)")
                        self.status_signal.emit("감지 타임아웃")
                        self.clicker.cleanup_auto_click(cdp)
                        self.click_result_signal.emit(False)
                        return
                else:
                    # 감지 전 대기
                    self.status_signal.emit(f"대기 중... ({remaining:.0f}초)")
                    if remaining < last_log_remaining - 300:
                        last_log_remaining = remaining
                        self.log_signal.emit(f"[대기] 남은: {remaining:.0f}초 ({remaining/60:.0f}분)")
                    if remaining > 120:
                        time.sleep(1.0)
                    elif remaining > 60:
                        time.sleep(0.5)
                    else:
                        time.sleep(0.1)

            self.log_signal.emit("[중지] 사용자 중지")
            self.status_signal.emit("중지됨")

        except Exception as e:
            self.log_signal.emit(f"[오류] {str(e)}")
            self.status_signal.emit("오류")
            self.click_result_signal.emit(False)

    def _handle_auto_click_success(self, cdp, auto_result: dict, poll_count: int):
        """브라우저 내부 자동클릭 성공 처리."""
        detect_time = self._now()
        diff_ms = (detect_time - self.target_timestamp) * 1000
        ax, ay = auto_result.get('x', 0), auto_result.get('y', 0)
        at = auto_result.get('text', '')
        src = auto_result.get('src', '?')
        js_elapsed = auto_result.get('elapsed', 0)  # JS 내부 경과시간

        btn_w = auto_result.get('w', 0)
        btn_h = auto_result.get('h', 0)
        btn_cls = auto_result.get('cls', '')
        btn_href = auto_result.get('href', '')

        self.log_signal.emit(f"[감지] ★★★ 브라우저 자동 클릭 성공! ★★★")
        self.log_signal.emit(f"[감지] 좌표: ({ax}, {ay}) | [{at}] | 출처: {src}")
        self.log_signal.emit(f"[감지] 버튼 크기: {btn_w}x{btn_h} | class: {btn_cls}")
        if btn_href:
            self.log_signal.emit(f"[감지] href: {btn_href}")
        self.log_signal.emit(f"[감지] JS 내부 감지→클릭: {js_elapsed}ms | 확인 시점: 목표 대비 {diff_ms:+.1f}ms")

        # ★ CDP 마우스 클릭으로 보강 (JS click이 안 먹는 경우 대비)
        # CDP 클릭은 OS 수준 입력을 시뮬레이션하므로 더 신뢰도 높음
        if ax > 0 and ay > 0:
            cdp.mouse_click(ax, ay)
            self.log_signal.emit(f"[클릭] CDP 보강 클릭 1차: ({ax}, {ay})")
            # 50ms 후 한 번 더 클릭 (첫 클릭이 무시될 수 있음)
            time.sleep(0.05)
            cdp.mouse_click(ax, ay)
            self.log_signal.emit(f"[클릭] CDP 보강 클릭 2차: ({ax}, {ay})")

        self.log_signal.emit(f"[클릭] ─────────────────────────────")
        self.log_signal.emit(f"[클릭] 결과: 성공 (브라우저 자동)")
        self.log_signal.emit(f"[클릭] ─────────────────────────────")

        self.status_signal.emit("클릭 성공!")
        self.log_signal.emit("[결과] 예매하기 버튼 클릭 성공!")
        self.log_signal.emit(">>> 예매하기 클릭 성공! 브라우저에서 확인하세요 <<<")
        self.click_result_signal.emit(True)

        # ★ 클릭 후 페이지 전환 모니터링 (전환 안 되면 재클릭 시도)
        self._monitor_page_after_click(cdp)

    # 좌표 재조회 스크립트 (폴백용)
    FRESH_COORDS_SCRIPT = """
    (function() {
        var sideBtns = document.querySelectorAll('a.sideBtn');
        for (var i = 0; i < sideBtns.length; i++) {
            var btn = sideBtns[i];
            if (btn.offsetHeight <= 0) continue;
            if (btn.textContent.indexOf('예매하기') >= 0) {
                var rect = btn.getBoundingClientRect();
                return {x: rect.x + rect.width/2, y: rect.y + rect.height/2, src: 'sideBtn'};
            }
        }
        var els = document.querySelectorAll('a, button, [role="button"]');
        for (var i = 0; i < els.length; i++) {
            var el = els[i];
            if (el.offsetHeight <= 0 || el.offsetWidth <= 0) continue;
            var t = el.textContent.trim();
            if (t.indexOf('예매하기') >= 0 && t.length < 100) {
                var rect = el.getBoundingClientRect();
                return {x: rect.x + rect.width/2, y: rect.y + rect.height/2, src: 'clickable'};
            }
        }
        return null;
    })()
    """

    def _do_click(self, cdp, state: dict):
        """폴링 감지 후 CDP 클릭 (자동클릭 폴백). 좌표 재조회 없이 즉시 클릭."""
        self.status_signal.emit("클릭 실행!")

        x = int(state.get('x', 0))
        y = int(state.get('y', 0))

        click_start = time.perf_counter()
        click_ntp = self._now()

        if x > 0 and y > 0:
            # ★ 좌표 재조회 제거 - 감지 시 받은 좌표로 즉시 클릭 (2.5초 절약)
            self.log_signal.emit(f"[클릭] 즉시 클릭: ({x}, {y})")
            cdp.mouse_click(x, y)
            success = True

            # JS 클릭도 병행 (CDP 클릭이 씹힐 경우 대비)
            try:
                cdp.execute_script(f"""
                (function() {{
                    var el = document.elementFromPoint({x}, {y});
                    if (el) {{
                        el.click();
                        var a = el.closest('a[href]');
                        if (a && a.href && a.href.indexOf('javascript:') < 0) {{
                            window.location.href = a.href;
                        }}
                    }}
                }})()
                """)
            except Exception:
                pass
        else:
            self.log_signal.emit("[클릭] 좌표 미확보 - JS 탐색")
            if self.clicker.prefetch_coords(cdp):
                success = self.clicker.click_now(cdp)
            else:
                success = False

        duration_ms = (time.perf_counter() - click_start) * 1000
        diff_ms = (click_ntp - self.target_timestamp) * 1000

        self.log_signal.emit(f"[클릭] ─────────────────────────────")
        self.log_signal.emit(f"[클릭] 결과: {'성공' if success else '실패'}")
        self.log_signal.emit(f"[클릭] 소요: {duration_ms:.2f}ms | 목표 대비: {diff_ms:+.1f}ms")
        self.log_signal.emit(f"[클릭] ─────────────────────────────")

        if success:
            self.status_signal.emit("클릭 성공!")
            self.log_signal.emit("[결과] 예매하기 버튼 클릭 성공!")
        else:
            self.status_signal.emit("버튼 미발견")
            self.log_signal.emit("[결과] 버튼을 찾을 수 없습니다")

        self.click_result_signal.emit(success)

        # ★ 클릭 후 페이지 전환 모니터링
        if success:
            self._monitor_page_after_click(cdp)

    # 페이지 상태 모니터링 스크립트
    PAGE_STATUS_SCRIPT = """
    (function() {
        var url = window.location.href;
        var readyState = document.readyState;
        var title = document.title || '';

        // 좌석 선택 페이지 감지 (URL 기반만 - DOM 오탐 방지)
        var isSeatPage = url.indexOf('Book/BookSeat') >= 0
            || url.indexOf('/book/') >= 0
            || url.indexOf('/Book/') >= 0
            || (url.indexOf('/Seat') >= 0 && url.indexOf('/goods/') < 0);

        // 대기열/큐 페이지 감지
        var isQueue = url.indexOf('queue') >= 0
            || url.indexOf('Queue') >= 0
            || url.indexOf('waiting') >= 0
            || title.indexOf('대기') >= 0
            || !!document.querySelector('[class*="queue"], [class*="waiting"]');

        // 에러 페이지 감지
        var isError = title.indexOf('오류') >= 0
            || title.indexOf('Error') >= 0
            || title.indexOf('에러') >= 0
            || !!document.querySelector('.error-page, .errorPage, [class*="error"]');

        // 페이지 내 주요 텍스트 (로딩/대기 메시지)
        var bodyText = '';
        try {
            var main = document.querySelector('main, .content, #content, body');
            if (main) bodyText = (main.innerText || '').substring(0, 300);
        } catch(e) {}

        var pendingMsg = '';
        if (bodyText.indexOf('잠시만 기다려') >= 0) pendingMsg = '잠시만 기다려주세요';
        else if (bodyText.indexOf('대기') >= 0 && bodyText.indexOf('번째') >= 0) {
            var m = bodyText.match(/(\\d+)\\s*번째/);
            pendingMsg = m ? m[0] + ' 대기 중' : '대기열';
        }
        else if (bodyText.indexOf('접속자가 많') >= 0) pendingMsg = '접속자 많음';
        else if (bodyText.indexOf('새로고침') >= 0) pendingMsg = '새로고침 필요';

        return {
            url: url,
            readyState: readyState,
            title: title.substring(0, 50),
            isSeatPage: isSeatPage,
            isQueue: isQueue,
            isError: isError,
            pendingMsg: pendingMsg
        };
    })()
    """

    def _monitor_page_after_click(self, cdp):
        """클릭 후 페이지 전환 상태를 30초간 모니터링. 전환 안 되면 재클릭 시도."""
        self.log_signal.emit("[모니터] ── 페이지 전환 모니터링 시작 ──")
        click_url = None
        try:
            click_url = cdp.get_current_url()
        except Exception:
            pass
        # URL에서 #만 제거해서 비교 기준 설정 (클릭 시 # 붙는 경우 대비)
        base_url = click_url.rstrip('#') if click_url else None
        self.log_signal.emit(f"[모니터] 클릭 시점 URL: {click_url or '확인 불가'}")

        start = time.perf_counter()
        check_count = 0
        last_state = None
        navigated = False
        retry_clicked = False

        while check_count < 30 and self.is_running:
            time.sleep(1.0)
            check_count += 1
            elapsed = time.perf_counter() - start

            try:
                status = cdp.execute_script(self.PAGE_STATUS_SCRIPT)
            except Exception:
                # 응답 없음 = 페이지 전환 중일 가능성 높음
                self.log_signal.emit(f"[모니터] {elapsed:.1f}초 | 페이지 로딩 중... (응답 없음)")
                self.status_signal.emit(f"페이지 로딩 중... ({elapsed:.0f}초)")
                navigated = True  # 응답이 없으면 전환 중으로 간주
                continue

            if not status:
                self.log_signal.emit(f"[모니터] {elapsed:.1f}초 | 페이지 전환 중...")
                self.status_signal.emit(f"페이지 전환 중... ({elapsed:.0f}초)")
                continue

            current_url = status.get('url', '')
            ready = status.get('readyState', '')
            title = status.get('title', '')
            current_base = current_url.rstrip('#') if current_url else ''

            # URL 변경 감지 (# 제거 후 비교)
            if base_url and current_base != base_url and not navigated:
                navigated = True
                self.log_signal.emit(f"[모니터] ★ 페이지 전환됨! ({elapsed:.1f}초)")
                self.log_signal.emit(f"[모니터] 새 URL: {current_url}")

            # 좌석 선택 페이지 도달
            if status.get('isSeatPage'):
                self.log_signal.emit(f"[모니터] ★★★ 좌석 선택 페이지 도달! ({elapsed:.1f}초) ★★★")
                self.status_signal.emit(f"좌석 선택 페이지! ({elapsed:.1f}초)")
                break

            # 대기열 감지
            if status.get('isQueue'):
                msg = status.get('pendingMsg', '대기열')
                self.log_signal.emit(f"[모니터] {elapsed:.1f}초 | 대기열: {msg}")
                self.status_signal.emit(f"대기열 ({msg})")
                continue

            # 에러 감지
            if status.get('isError'):
                self.log_signal.emit(f"[모니터] {elapsed:.1f}초 | 에러 페이지 감지!")
                self.status_signal.emit("에러 페이지!")
                break

            # 대기 메시지
            pending = status.get('pendingMsg', '')
            if pending:
                self.log_signal.emit(f"[모니터] {elapsed:.1f}초 | {pending}")
                self.status_signal.emit(f"{pending} ({elapsed:.0f}초)")
                continue

            # ★ 3초 지나도 URL 안 바뀌면 재클릭 시도
            if check_count == 3 and not navigated and not retry_clicked:
                retry_clicked = True
                self.log_signal.emit(f"[모니터] ⚠ 3초 경과 - 페이지 전환 없음! 재클릭 시도...")
                try:
                    coords = cdp.execute_script(self.FRESH_COORDS_SCRIPT)
                    if coords and coords.get('x', 0) > 0:
                        rx, ry = int(coords['x']), int(coords['y'])
                        cdp.mouse_click(rx, ry)
                        self.log_signal.emit(f"[모니터] 재클릭: ({rx}, {ry}) | {coords.get('src', '?')}")
                        # JS 클릭도 추가로 시도
                        cdp.execute_script("""
                        (function() {
                            var btns = document.querySelectorAll('a.sideBtn');
                            for (var i = 0; i < btns.length; i++) {
                                if (btns[i].textContent.indexOf('예매하기') >= 0 && btns[i].offsetHeight > 0) {
                                    btns[i].click();
                                    return 'clicked';
                                }
                            }
                            return 'not_found';
                        })()
                        """)
                    else:
                        self.log_signal.emit(f"[모니터] 재클릭 대상 없음 (버튼 사라짐)")
                except Exception as e:
                    self.log_signal.emit(f"[모니터] 재클릭 실패: {e}")

            # 일반 상태 (5초마다 로그)
            state_key = f"{current_url}|{ready}"
            if state_key != last_state:
                last_state = state_key
                self.log_signal.emit(
                    f"[모니터] {elapsed:.1f}초 | {ready} | {title}"
                )
            elif check_count % 5 == 0:
                self.log_signal.emit(
                    f"[모니터] {elapsed:.1f}초 | {ready} | 변화 없음"
                )

            self.status_signal.emit(
                f"클릭 완료 - {ready} ({elapsed:.0f}초)"
            )

        total = time.perf_counter() - start
        self.log_signal.emit(f"[모니터] ── 모니터링 종료 ({total:.1f}초) ──")

    def stop(self):
        self.is_running = False

    def cleanup(self):
        self.is_running = False
        if self.browser.cdp:
            self.clicker.cleanup_auto_click(self.browser.cdp)
        self.browser.disconnect()
