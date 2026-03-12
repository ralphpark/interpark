import json
import os
import glob
import subprocess
import platform
import tempfile
import time
import urllib.request

import websocket


def find_chrome_path() -> str | None:
    """OS별 Chrome 실행파일 경로 자동 탐색."""
    system = platform.system()

    if system == "Windows":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    elif system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    if system == "Windows":
        for pattern in [r"C:\Program Files*\Google\Chrome\Application\chrome.exe"]:
            matches = glob.glob(pattern)
            if matches:
                return matches[0]

    return None


class CDPConnection:
    """Chrome DevTools Protocol 직접 WebSocket 연결.
    Selenium/ChromeDriver 없이 Chrome과 직접 통신.
    """

    def __init__(self, debug_port: int = 9222):
        self.debug_port = debug_port
        self._ws = None
        self._msg_id = 0
        self._last_error = None

    def connect(self) -> bool:
        """Chrome CDP WebSocket에 연결."""
        try:
            resp = urllib.request.urlopen(
                f'http://127.0.0.1:{self.debug_port}/json',
                timeout=5,
            )
            targets = json.loads(resp.read())
            page_targets = [t for t in targets if t.get('type') == 'page']
            if not page_targets:
                self._last_error = "페이지 타겟 없음 (Chrome 탭이 없습니다)"
                return False
            ws_url = page_targets[0].get('webSocketDebuggerUrl')
            if not ws_url:
                self._last_error = "WebSocket URL 없음 (다른 프로그램이 연결 중일 수 있습니다)"
                return False
            self._ws = websocket.create_connection(ws_url, timeout=10)
            self._last_error = None
            return True
        except urllib.error.URLError as e:
            self._last_error = f"Chrome 디버그 포트 연결 실패: {e.reason}"
        except Exception as e:
            self._last_error = f"연결 오류: {str(e)}"
        return False

    @property
    def last_error(self) -> str:
        return self._last_error or "알 수 없는 오류"

    def _send(self, method: str, params: dict = None, timeout: float = 10.0) -> dict:
        """CDP 명령 전송 + 응답 대기 (타임아웃 + 이벤트 무시)."""
        self._msg_id += 1
        msg_id = self._msg_id
        self._ws.send(json.dumps({
            'id': msg_id,
            'method': method,
            'params': params or {},
        }))
        deadline = time.time() + timeout
        old_timeout = self._ws.gettimeout()
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"CDP response timeout: {method} (>{timeout}s)")
            self._ws.settimeout(min(remaining, 1.0))
            try:
                resp = json.loads(self._ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if resp.get('id') == msg_id:
                self._ws.settimeout(old_timeout)
                return resp
            # event or other response - ignore

    def _fire(self, method: str, params: dict = None):
        """CDP 명령 전송 (응답 대기 없음). 클릭 등 속도가 중요한 곳에 사용."""
        self._msg_id += 1
        self._ws.send(json.dumps({
            'id': self._msg_id,
            'method': method,
            'params': params or {},
        }))

    def register_script(self, name: str, script: str):
        """JS 함수를 브라우저에 등록 (한 번만 전송, 이후 호출만)."""
        # Wrap script as a named function on window object
        wrapped = f"window.__avocado_{name} = function() {{ return ({script}); }}"
        self._send('Runtime.evaluate', {'expression': wrapped, 'returnByValue': True})

    def execute_registered(self, name: str):
        """등록된 JS 함수 호출 (경량 호출)."""
        resp = self._send('Runtime.evaluate', {
            'expression': f'window.__avocado_{name} ? window.__avocado_{name}() : null',
            'returnByValue': True,
        })
        result = resp.get('result', {}).get('result', {})
        return result.get('value')

    def execute_script(self, script: str):
        """JavaScript 실행 (Runtime.evaluate)."""
        resp = self._send('Runtime.evaluate', {
            'expression': script,
            'returnByValue': True,
        })
        result = resp.get('result', {}).get('result', {})
        return result.get('value')

    def get_current_url(self) -> str:
        return self.execute_script('window.location.href') or ''

    def refresh(self):
        self._send('Page.reload')

    def mouse_move(self, x: int, y: int):
        """마우스 이동 (hover 상태 확보용)."""
        self._fire('Input.dispatchMouseEvent', {
            'type': 'mouseMoved',
            'x': x, 'y': y,
        })

    def mouse_click(self, x: int, y: int):
        """마우스 클릭 (mousePressed + mouseReleased). 응답 대기 없이 즉시 전송."""
        self._fire('Input.dispatchMouseEvent', {
            'type': 'mousePressed',
            'x': x, 'y': y,
            'button': 'left', 'clickCount': 1,
        })
        self._fire('Input.dispatchMouseEvent', {
            'type': 'mouseReleased',
            'x': x, 'y': y,
            'button': 'left', 'clickCount': 1,
        })

    def close(self):
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass


class BrowserManager:
    """Chrome 실행 + CDP 직접 연결 관리."""

    def __init__(self):
        self.cdp = None
        self._chrome_process = None

    def launch_chrome_debug(self, debug_port: int = 9222) -> str | None:
        """Chrome을 디버깅 모드로 실행."""
        chrome_path = find_chrome_path()
        if not chrome_path:
            return None

        profile_dir = os.path.join(tempfile.gettempdir(), "interpark-macro-chrome")
        os.makedirs(profile_dir, exist_ok=True)

        try:
            self._chrome_process = subprocess.Popen(
                [
                    chrome_path,
                    f"--remote-debugging-port={debug_port}",
                    f"--user-data-dir={profile_dir}",
                    "--remote-allow-origins=*",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
            return chrome_path
        except Exception:
            return None

    def connect(self, debug_port: int = 9222) -> bool:
        """Chrome CDP에 직접 연결."""
        self.cdp = CDPConnection(debug_port)
        return self.cdp.connect()

    def disconnect(self):
        if self.cdp:
            self.cdp.close()
            self.cdp = None
