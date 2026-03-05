from src.core.browser import CDPConnection


class TicketClicker:
    """예매하기 버튼 클릭 엔진. Chrome CDP 직접 통신."""

    FIND_BUTTON_SCRIPT = """
    (function() {
        // 팝업 닫기
        var closeBtns = document.querySelectorAll(
            'button.popupCloseBtn, .popupClose, [class*="popupClose"]'
        );
        for (var i = 0; i < closeBtns.length; i++) {
            if (closeBtns[i].offsetHeight > 0) closeBtns[i].click();
        }
        var popups = document.querySelectorAll('.popup.is-visible');
        for (var i = 0; i < popups.length; i++) {
            popups[i].classList.remove('is-visible');
        }

        // 버튼 찾기
        var btn = document.querySelector('a.sideBtn.is-primary');
        if (!btn || btn.offsetHeight <= 0) {
            var sideBtns = document.querySelectorAll('a.sideBtn');
            for (var i = 0; i < sideBtns.length; i++) {
                if (sideBtns[i].textContent.indexOf('예매하기') >= 0 && sideBtns[i].offsetHeight > 0) {
                    btn = sideBtns[i]; break;
                }
            }
        }
        if (!btn || btn.offsetHeight <= 0) {
            var spans = document.querySelectorAll('span');
            for (var i = 0; i < spans.length; i++) {
                if (spans[i].textContent.trim() === '예매하기' && spans[i].offsetWidth > 50) {
                    btn = spans[i].closest('a, button') || spans[i]; break;
                }
            }
        }
        if (!btn) return null;
        var rect = btn.getBoundingClientRect();
        return {x: rect.x + rect.width / 2, y: rect.y + rect.height / 2};
    })()
    """

    def __init__(self):
        self._cached_coords = None

    def prefetch_coords(self, cdp: CDPConnection) -> bool:
        """목표 시간 전에 미리 버튼 좌표를 찾아 캐시 + hover 상태 확보."""
        try:
            coords = cdp.execute_script(self.FIND_BUTTON_SCRIPT)
            if coords:
                self._cached_coords = coords
                cdp.mouse_move(int(coords['x']), int(coords['y']))
                return True
        except Exception:
            pass
        return False

    def click_now(self, cdp: CDPConnection) -> bool:
        """캐시된 좌표로 CDP 마우스 클릭. ~20ms."""
        coords = self._cached_coords
        if not coords:
            return False
        try:
            cdp.mouse_click(int(coords['x']), int(coords['y']))
            return True
        except Exception:
            pass
        return False
