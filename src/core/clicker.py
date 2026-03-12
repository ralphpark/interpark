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

        // 1) a.sideBtn에서 찾기
        var btn = document.querySelector('a.sideBtn.is-primary');
        if (!btn || btn.offsetHeight <= 0) {
            var sideBtns = document.querySelectorAll('a.sideBtn');
            for (var i = 0; i < sideBtns.length; i++) {
                var t = sideBtns[i].textContent;
                if ((t.indexOf('예매하기') >= 0 || t.indexOf('남은시간') >= 0 || t.indexOf('남은 시간') >= 0)
                    && sideBtns[i].offsetHeight > 0) {
                    btn = sideBtns[i]; break;
                }
            }
        }

        // 2) 모든 클릭 가능 요소에서 "예매하기" 찾기
        if (!btn || btn.offsetHeight <= 0) {
            var clickables = document.querySelectorAll('a, button, [role="button"], [onclick], [class*="booking"], [class*="reserve"], [class*="ticket"]');
            for (var i = 0; i < clickables.length; i++) {
                var el = clickables[i];
                if (el.offsetHeight <= 0 || el.offsetWidth <= 0) continue;
                var text = el.textContent.trim();
                if (text.indexOf('예매하기') >= 0 && text.length < 100) {
                    btn = el; break;
                }
            }
        }

        // 3) span/div 내부 "예매하기" → 부모 요소
        if (!btn || btn.offsetHeight <= 0) {
            var textEls = document.querySelectorAll('span, div, strong');
            for (var i = 0; i < textEls.length; i++) {
                if (textEls[i].textContent.trim() === '예매하기' && textEls[i].offsetWidth > 30) {
                    btn = textEls[i].closest('a, button, [role="button"]') || textEls[i];
                    break;
                }
            }
        }

        if (!btn) return null;
        var rect = btn.getBoundingClientRect();
        return {x: rect.x + rect.width / 2, y: rect.y + rect.height / 2};
    })()
    """

    # 버튼 상태 감지 스크립트: 텍스트 + 배경색으로 "오픈 예정" vs "오픈(예매하기)" 판별
    CHECK_BUTTON_STATE_SCRIPT = """
    (function() {
        function parseColor(color) {
            var m = color.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
            if (!m) return null;
            return {r: parseInt(m[1]), g: parseInt(m[2]), b: parseInt(m[3])};
        }
        function isBlueish(color) {
            var c = parseColor(color);
            return c && (c.b > 150 && c.b > c.r && c.b > c.g);
        }
        function isGrayish(color) {
            var c = parseColor(color);
            if (!c) return false;
            var max = Math.max(c.r,c.g,c.b), min = Math.min(c.r,c.g,c.b);
            return (max - min < 40 && max < 200);
        }
        function isPinkOrRed(color) {
            var c = parseColor(color);
            return c && (c.r > 150 && c.r > c.g && c.r > c.b);
        }
        function isColorful(color) {
            // 회색/투명이 아닌 유채색인지 (오픈 상태 버튼)
            var c = parseColor(color);
            if (!c) return false;
            var max = Math.max(c.r,c.g,c.b), min = Math.min(c.r,c.g,c.b);
            return (max - min > 40) || (max > 200);
        }
        function isDisabled(el) {
            if (el.classList.contains('is-disabled')) return true;
            if (el.hasAttribute('disabled')) return true;
            if (el.getAttribute('aria-disabled') === 'true') return true;
            var style = window.getComputedStyle(el);
            if (style.pointerEvents === 'none') return true;
            return false;
        }
        function getEffectiveBg(el) {
            // 자신과 부모의 배경색 중 투명이 아닌 첫 번째
            var cur = el;
            for (var d = 0; d < 5 && cur; d++) {
                var bg = window.getComputedStyle(cur).backgroundColor;
                var c = parseColor(bg);
                if (c && (c.r > 0 || c.g > 0 || c.b > 0)) return bg;
                cur = cur.parentElement;
            }
            return 'rgba(0,0,0,0)';
        }
        function makeResult(state, el, text, bgColor, extra) {
            var res = {state: state, text: text, color: bgColor};
            if (state === 'open' && el) {
                var rect = el.getBoundingClientRect();
                res.x = rect.x + rect.width/2;
                res.y = rect.y + rect.height/2;
            }
            if (extra) { for (var k in extra) res[k] = extra[k]; }
            return res;
        }

        // ── 0단계: 달력 + 회차가 표시되어야 진짜 open ──
        function isBookingPageReady() {
            var calendarReady = false;
            var dateCells = document.querySelectorAll('.calendarWrap td a, .calendar td a, [class*="calendar"] td a, [class*="Calendar"] td a');
            if (dateCells.length > 0) {
                for (var i = 0; i < dateCells.length; i++) {
                    if (dateCells[i].offsetHeight > 0) { calendarReady = true; break; }
                }
            }
            if (!calendarReady) {
                var calArea = document.querySelector('.calendarWrap, [class*="calendar"], [class*="Calendar"]');
                if (calArea && calArea.offsetHeight > 100) {
                    var t = calArea.innerText || '';
                    if (t.indexOf('일') >= 0 && t.indexOf('월') >= 0 && /\\d{1,2}/.test(t)) calendarReady = true;
                }
            }
            var timeReady = false;
            var timeEls = document.querySelectorAll('[class*="time"], [class*="session"], [class*="round"], .sideContent li, .sideContent a');
            for (var i = 0; i < timeEls.length; i++) {
                var txt = timeEls[i].textContent || '';
                if (/\\d+회/.test(txt) && /\\d{1,2}:\\d{2}/.test(txt) && timeEls[i].offsetHeight > 0) { timeReady = true; break; }
            }
            if (!timeReady) {
                var sideArea = document.querySelector('.sideContent, [class*="side"], .scheduleWrap');
                if (sideArea) {
                    var st = sideArea.innerText || '';
                    if (/회차/.test(st) && /\\d+회[\\s\\S]*?\\d{1,2}:\\d{2}/.test(st)) timeReady = true;
                }
            }
            return calendarReady && timeReady;
        }
        var pageReady = isBookingPageReady();

        // ── 1단계: a.sideBtn 순회 (가장 일반적인 케이스) ──
        var sideBtns = document.querySelectorAll('a.sideBtn');
        for (var i = 0; i < sideBtns.length; i++) {
            var btn = sideBtns[i];
            if (btn.offsetHeight <= 0) continue;
            var text = btn.textContent.trim();
            var bgColor = getEffectiveBg(btn);

            // "예매하기" 텍스트 → 색상/상태로 open vs pending 판별
            if (text.indexOf('예매하기') >= 0) {
                if (isDisabled(btn) || isGrayish(bgColor)) {
                    return makeResult('pending', null, text, bgColor);
                }
                // ★ 달력+회차 미표시 → 아직 로딩 중 (pending)
                if (!pageReady) {
                    return makeResult('pending', null, text, bgColor, {reason: 'page_not_ready'});
                }
                return makeResult('open', btn, text, bgColor);
            }
            // "남은시간" 카운트다운
            if (text.indexOf('남은시간') >= 0 || text.indexOf('남은 시간') >= 0) {
                var cd = text.match(/(\\d{1,2}:\\d{2}(?::\\d{2})?)/);
                return makeResult('pending', null, text, bgColor, {countdown: cd ? cd[1] : null, type: 'countdown'});
            }
            // "일반예매" / "오픈예정"
            if (text.indexOf('일반예매') >= 0 || text.indexOf('오픈예정') >= 0 || text.indexOf('오픈 예정') >= 0) {
                return makeResult('pending', null, text, bgColor);
            }
        }

        // ── 2단계: 모든 클릭 가능 요소에서 "예매하기" 광범위 탐색 ──
        //   (카운트다운 종료 후 버튼이 a.sideBtn이 아닌 다른 요소로 바뀔 수 있음)
        var clickables = document.querySelectorAll('a, button, [role="button"], [onclick], .sideBtn, [class*="booking"], [class*="reserve"], [class*="ticket"]');
        for (var i = 0; i < clickables.length; i++) {
            var el = clickables[i];
            if (el.offsetHeight <= 0 || el.offsetWidth <= 0) continue;
            // 이미 sideBtn으로 체크한 요소 스킵
            if (el.tagName === 'A' && el.classList.contains('sideBtn')) continue;
            var text = el.textContent.trim();
            if (text.indexOf('예매하기') < 0) continue;
            // 텍스트가 너무 길면 (100자 이상) 상위 컨테이너일 가능성 → 스킵
            if (text.length > 100) continue;
            var bgColor = getEffectiveBg(el);
            if (isDisabled(el) || isGrayish(bgColor)) {
                return makeResult('pending', null, text, bgColor);
            }
            // ★ 달력+회차 미표시 → 아직 로딩 중 (pending)
            if (!pageReady) {
                return makeResult('pending', null, text, bgColor, {reason: 'page_not_ready'});
            }
            return makeResult('open', el, text, bgColor);
        }

        // ── 3단계: span/div 내부의 "예매하기" 텍스트 (부모 요소로 좌표 확보) ──
        var textEls = document.querySelectorAll('span, div, p, strong, em');
        for (var i = 0; i < textEls.length; i++) {
            var el = textEls[i];
            var text = el.textContent.trim();
            if (text !== '예매하기' && text !== '예매 하기') continue;
            if (el.offsetWidth < 30 || el.offsetHeight < 10) continue;
            var clickParent = el.closest('a, button, [role="button"], [onclick]') || el;
            var bgColor = getEffectiveBg(clickParent);
            if (isDisabled(clickParent) || isGrayish(bgColor)) {
                return makeResult('pending', null, text, bgColor);
            }
            // ★ 달력+회차 미표시 → 아직 로딩 중 (pending)
            if (!pageReady) {
                return makeResult('pending', null, text, bgColor, {reason: 'page_not_ready'});
            }
            return makeResult('open', clickParent, text, bgColor);
        }

        // ── 4단계: "남은시간" 카운트다운 (sideBtn 외부) ──
        var allEls = document.querySelectorAll('a, button, div, span');
        for (var i = 0; i < allEls.length; i++) {
            var el = allEls[i];
            if (el.offsetHeight <= 0 || el.offsetHeight > 100) continue;
            var text = el.textContent.trim();
            if (text.length > 50) continue;
            if (text.indexOf('남은시간') >= 0 || text.indexOf('남은 시간') >= 0) {
                if (el.closest('a.sideBtn')) continue;
                var bgColor = getEffectiveBg(el);
                var cd = text.match(/(\\d{1,2}:\\d{2}(?::\\d{2})?)/);
                return makeResult('pending', null, text, bgColor, {countdown: cd ? cd[1] : null, type: 'countdown'});
            }
        }

        return {state: 'unknown'};
    })()
    """

    # 버튼 텍스트에서 날짜/시간 추출 스크립트
    PARSE_BUTTON_TIME_SCRIPT = """
    (function() {
        // 1) sideBtn에서 "03/11 20:00 일반예매" 패턴
        var sideBtns = document.querySelectorAll('a.sideBtn');
        for (var i = 0; i < sideBtns.length; i++) {
            var btn = sideBtns[i];
            if (btn.offsetHeight <= 0) continue;
            var text = btn.textContent.trim();
            var m = text.match(/(\\d{1,2})\\/(\\d{1,2})\\s+(\\d{1,2}):(\\d{2})/);
            if (m) {
                return {month: parseInt(m[1]), day: parseInt(m[2]), hour: parseInt(m[3]), minute: parseInt(m[4]), text: text};
            }
        }

        // 2) "티켓오픈안내" 영역에서 "2026.03.11 10:00" 또는 "2026-03-11 10:00" 패턴
        var body = document.body ? document.body.innerText : '';
        // "yyyy.MM.dd HH:mm" 패턴
        var m2 = body.match(/티켓\\s*오픈[\\s\\S]{0,50}?(\\d{4})[.\\-/](\\d{1,2})[.\\-/](\\d{1,2})\\s+(\\d{1,2}):(\\d{2})/);
        if (m2) {
            return {year: parseInt(m2[1]), month: parseInt(m2[2]), day: parseInt(m2[3]),
                    hour: parseInt(m2[4]), minute: parseInt(m2[5]),
                    text: '티켓오픈 ' + m2[1] + '.' + m2[2] + '.' + m2[3] + ' ' + m2[4] + ':' + m2[5],
                    source: 'ticket_open_info'};
        }

        // 3) "MM/dd HH:mm" 또는 "MM.dd HH:mm" 패턴 (페이지 전체)
        var m3 = body.match(/오픈[\\s\\S]{0,30}?(\\d{1,2})[./](\\d{1,2})\\s+(\\d{1,2}):(\\d{2})/);
        if (m3) {
            return {month: parseInt(m3[1]), day: parseInt(m3[2]),
                    hour: parseInt(m3[3]), minute: parseInt(m3[4]),
                    text: '오픈 ' + m3[1] + '/' + m3[2] + ' ' + m3[3] + ':' + m3[4],
                    source: 'page_text'};
        }

        return null;
    })()
    """

    # ★ 브라우저 내부 고속 자동클릭 (setInterval 5ms + MutationObserver)
    # 달력+회차가 보여야만 클릭 (중간 상태의 가짜 예매하기 버튼 방지)
    # 페이지 리로드 시 자동 재설치 불가 → scheduler에서 주기적 재설치
    INJECT_AUTO_CLICK_SCRIPT = """
    (function() {
        if (window.__avocadoTimer) {
            return {status: 'already_installed', clicked: !!window.__avocadoClicked};
        }
        window.__avocadoClicked = null;
        window.__avocadoLog = [];
        window.__avocadoStartTime = Date.now();

        function isPageReady() {
            // ★ 경량화: 달력 영역 존재 + 회차 시간 패턴만 체크
            var calOk = false;
            var cal = document.querySelector('.calendarWrap, [class*="calendar"], [class*="Calendar"]');
            if (cal && cal.offsetHeight > 50) calOk = true;
            if (!calOk) {
                var tds = document.querySelectorAll('.calendarWrap td a, .calendar td a');
                if (tds.length > 0) calOk = true;
            }

            var timeOk = false;
            var side = document.querySelector('.sideContent, [class*="side"], .scheduleWrap');
            if (side) {
                var t = side.innerText || '';
                if (/\\d+회/.test(t) && /\\d{1,2}:\\d{2}/.test(t)) timeOk = true;
            }
            if (!timeOk) {
                var els = document.querySelectorAll('[class*="time"], [class*="round"], .sideContent li');
                for (var i = 0; i < els.length; i++) {
                    var txt = els[i].textContent || '';
                    if (/\\d+회/.test(txt) && /\\d{1,2}:\\d{2}/.test(txt) && els[i].offsetHeight > 0) {
                        timeOk = true; break;
                    }
                }
            }
            return calOk && timeOk;
        }

        function findAndClick() {
            if (window.__avocadoClicked) return;
            if (!isPageReady()) return;

            // 1) a.sideBtn
            var sideBtns = document.querySelectorAll('a.sideBtn');
            for (var i = 0; i < sideBtns.length; i++) {
                var btn = sideBtns[i];
                if (btn.offsetHeight <= 0) continue;
                var text = btn.textContent.trim();
                if (text.indexOf('남은시간') >= 0 || text.indexOf('남은 시간') >= 0) continue;
                if (text.indexOf('일반예매') >= 0 || text.indexOf('오픈예정') >= 0) continue;
                if (text.indexOf('예매하기') >= 0) {
                    if (btn.classList.contains('is-disabled')) continue;
                    doClick(btn, 'sideBtn');
                    return;
                }
            }
            // 2) 모든 a, button 요소
            var els = document.querySelectorAll('a, button, [role="button"]');
            for (var i = 0; i < els.length; i++) {
                var el = els[i];
                if (el.offsetHeight <= 0 || el.offsetWidth <= 0) continue;
                if (el.tagName === 'A' && el.classList.contains('sideBtn')) continue;
                var text = el.textContent.trim();
                if (text.indexOf('예매하기') >= 0 && text.length < 50) {
                    doClick(el, 'other');
                    return;
                }
            }
        }

        function doClick(btn, src) {
            var rect = btn.getBoundingClientRect();
            var x = rect.x + rect.width/2, y = rect.y + rect.height/2;
            var now = Date.now();
            var elapsed = now - window.__avocadoStartTime;

            // 클릭 실행 (3중: .click + mousedown/up + MouseEvent)
            btn.click();
            btn.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));
            btn.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));
            btn.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));

            // href가 있으면 직접 네비게이션도 시도 (클릭 이벤트가 씹힐 경우 대비)
            if (btn.href && btn.href.indexOf('javascript:') < 0) {
                setTimeout(function() { window.location.href = btn.href; }, 50);
            }

            window.__avocadoClicked = {
                time: now, x: Math.round(x), y: Math.round(y),
                text: btn.textContent.trim().substring(0, 30), src: src,
                elapsed: elapsed
            };
            if (window.__avocadoTimer) {
                clearInterval(window.__avocadoTimer);
                window.__avocadoTimer = null;
            }
            if (window.__avocadoObserver) {
                window.__avocadoObserver.disconnect();
                window.__avocadoObserver = null;
            }
        }

        // ★ 이중 감시: setInterval(5ms) + MutationObserver
        window.__avocadoTimer = setInterval(findAndClick, 5);

        // MutationObserver: DOM 변경 즉시 감지 (5ms보다 빠를 수 있음)
        try {
            window.__avocadoObserver = new MutationObserver(function() {
                findAndClick();
            });
            window.__avocadoObserver.observe(document.body || document.documentElement, {
                childList: true, subtree: true, attributes: true, characterData: true
            });
        } catch(e) {
            window.__avocadoLog.push('observer_error: ' + e.message);
        }

        // 안전장치: 60초 후 자동 해제
        setTimeout(function() {
            if (window.__avocadoTimer) {
                clearInterval(window.__avocadoTimer);
                window.__avocadoTimer = null;
            }
            if (window.__avocadoObserver) {
                window.__avocadoObserver.disconnect();
                window.__avocadoObserver = null;
            }
        }, 60000);

        return {status: 'installed', interval: 5};
    })()
    """

    # 자동 클릭 결과 확인
    CHECK_AUTO_CLICK_RESULT_SCRIPT = """
    (function() {
        if (window.__avocadoClicked) {
            var r = window.__avocadoClicked;
            return {clicked: true, time: r.time, x: r.x, y: r.y, text: r.text, src: r.src, elapsed: r.elapsed || 0};
        }
        return {clicked: false, timerActive: !!window.__avocadoTimer};
    })()
    """

    # ★ 통합 상태 체크: 자동클릭 결과 + 버튼 상태를 한 번의 CDP 호출로 확인
    COMBINED_CHECK_SCRIPT = """
    (function() {
        var result = {autoClicked: null, buttonState: null};

        // 1) 자동클릭 결과 확인
        if (window.__avocadoClicked) {
            var r = window.__avocadoClicked;
            result.autoClicked = {clicked: true, time: r.time, x: r.x, y: r.y, text: r.text, src: r.src, elapsed: r.elapsed || 0};
            return result;
        }
        result.autoClickActive = !!window.__avocadoTimer;

        // 2) 버튼 상태 확인 (경량 버전)
        function parseColor(color) {
            var m = color.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
            if (!m) return null;
            return {r: parseInt(m[1]), g: parseInt(m[2]), b: parseInt(m[3])};
        }
        function isGrayish(color) {
            var c = parseColor(color);
            if (!c) return false;
            var max = Math.max(c.r,c.g,c.b), min = Math.min(c.r,c.g,c.b);
            return (max - min < 40 && max < 200);
        }
        function isDisabled(el) {
            if (el.classList.contains('is-disabled')) return true;
            if (el.hasAttribute('disabled')) return true;
            if (el.getAttribute('aria-disabled') === 'true') return true;
            var style = window.getComputedStyle(el);
            if (style.pointerEvents === 'none') return true;
            return false;
        }
        function getEffectiveBg(el) {
            var cur = el;
            for (var d = 0; d < 5 && cur; d++) {
                var bg = window.getComputedStyle(cur).backgroundColor;
                var c = parseColor(bg);
                if (c && (c.r > 0 || c.g > 0 || c.b > 0)) return bg;
                cur = cur.parentElement;
            }
            return 'rgba(0,0,0,0)';
        }

        // 달력+회차 체크 (경량)
        var calOk = false;
        var cal = document.querySelector('.calendarWrap, [class*="calendar"], [class*="Calendar"]');
        if (cal && cal.offsetHeight > 50) calOk = true;
        if (!calOk) {
            var tds = document.querySelectorAll('.calendarWrap td a, .calendar td a');
            if (tds.length > 0) calOk = true;
        }
        var timeOk = false;
        var side = document.querySelector('.sideContent, [class*="side"], .scheduleWrap');
        if (side) {
            var t = side.innerText || '';
            if (/\\d+회/.test(t) && /\\d{1,2}:\\d{2}/.test(t)) timeOk = true;
        }
        if (!timeOk) {
            var els = document.querySelectorAll('[class*="time"], [class*="round"], .sideContent li');
            for (var i = 0; i < els.length; i++) {
                var txt = els[i].textContent || '';
                if (/\\d+회/.test(txt) && /\\d{1,2}:\\d{2}/.test(txt) && els[i].offsetHeight > 0) {
                    timeOk = true; break;
                }
            }
        }
        var pageReady = calOk && timeOk;

        // sideBtn 순회
        var sideBtns = document.querySelectorAll('a.sideBtn');
        for (var i = 0; i < sideBtns.length; i++) {
            var btn = sideBtns[i];
            if (btn.offsetHeight <= 0) continue;
            var text = btn.textContent.trim();
            var bgColor = getEffectiveBg(btn);

            if (text.indexOf('예매하기') >= 0) {
                if (isDisabled(btn) || isGrayish(bgColor)) {
                    result.buttonState = {state: 'pending', text: text, color: bgColor};
                    return result;
                }
                if (!pageReady) {
                    result.buttonState = {state: 'pending', text: text, color: bgColor, reason: 'page_not_ready'};
                    return result;
                }
                var rect = btn.getBoundingClientRect();
                result.buttonState = {state: 'open', text: text, color: bgColor, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                return result;
            }
            if (text.indexOf('남은시간') >= 0 || text.indexOf('남은 시간') >= 0) {
                var cd = text.match(/(\\d{1,2}:\\d{2}(?::\\d{2})?)/);
                result.buttonState = {state: 'pending', text: text, color: bgColor, countdown: cd ? cd[1] : null, type: 'countdown'};
                return result;
            }
            if (text.indexOf('일반예매') >= 0 || text.indexOf('오픈예정') >= 0 || text.indexOf('오픈 예정') >= 0) {
                result.buttonState = {state: 'pending', text: text, color: bgColor};
                return result;
            }
        }

        // 모든 클릭 가능 요소
        var clickables = document.querySelectorAll('a, button, [role="button"], [onclick], .sideBtn, [class*="booking"], [class*="reserve"], [class*="ticket"]');
        for (var i = 0; i < clickables.length; i++) {
            var el = clickables[i];
            if (el.offsetHeight <= 0 || el.offsetWidth <= 0) continue;
            if (el.tagName === 'A' && el.classList.contains('sideBtn')) continue;
            var text = el.textContent.trim();
            if (text.indexOf('예매하기') < 0 || text.length > 100) continue;
            var bgColor = getEffectiveBg(el);
            if (isDisabled(el) || isGrayish(bgColor)) {
                result.buttonState = {state: 'pending', text: text, color: bgColor};
                return result;
            }
            if (!pageReady) {
                result.buttonState = {state: 'pending', text: text, color: bgColor, reason: 'page_not_ready'};
                return result;
            }
            var rect = el.getBoundingClientRect();
            result.buttonState = {state: 'open', text: text, color: bgColor, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
            return result;
        }

        result.buttonState = {state: 'unknown'};
        return result;
    })()
    """

    # 해제 스크립트
    CLEANUP_AUTO_CLICK_SCRIPT = """
    (function() {
        if (window.__avocadoTimer) {
            clearInterval(window.__avocadoTimer);
            window.__avocadoTimer = null;
        }
        if (window.__avocadoObserver) {
            window.__avocadoObserver.disconnect();
            window.__avocadoObserver = null;
        }
        window.__avocadoClicked = null;
    })()
    """

    def __init__(self):
        self._cached_coords = None

    def check_button_state(self, cdp: CDPConnection) -> dict | None:
        """버튼 상태 확인. 'open'=예매가능, 'pending'=오픈예정, 'unknown'=불명."""
        try:
            return cdp.execute_script(self.CHECK_BUTTON_STATE_SCRIPT)
        except Exception:
            return None

    def parse_button_time(self, cdp: CDPConnection) -> dict | None:
        """버튼 텍스트에서 날짜/시간 파싱. {month, day, hour, minute, text}."""
        try:
            return cdp.execute_script(self.PARSE_BUTTON_TIME_SCRIPT)
        except Exception:
            return None

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

    def click_at(self, cdp: CDPConnection, x: int, y: int) -> bool:
        """지정 좌표로 즉시 클릭."""
        try:
            cdp.mouse_click(x, y)
            return True
        except Exception:
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

    def inject_auto_click(self, cdp: CDPConnection) -> dict | None:
        """브라우저 내부 고속 자동클릭 설치. 10ms 간격으로 예매하기 감지 즉시 클릭."""
        try:
            return cdp.execute_script(self.INJECT_AUTO_CLICK_SCRIPT)
        except Exception:
            return None

    def check_auto_click_result(self, cdp: CDPConnection) -> dict | None:
        """자동 클릭 결과 확인."""
        try:
            return cdp.execute_script(self.CHECK_AUTO_CLICK_RESULT_SCRIPT)
        except Exception:
            return None

    def combined_check(self, cdp) -> dict | None:
        """자동클릭 결과 + 버튼 상태를 한 번의 CDP 호출로 확인."""
        try:
            return cdp.execute_script(self.COMBINED_CHECK_SCRIPT)
        except Exception:
            return None

    def cleanup_auto_click(self, cdp: CDPConnection):
        """자동 클릭 타이머 해제."""
        try:
            cdp.execute_script(self.CLEANUP_AUTO_CLICK_SCRIPT)
        except Exception:
            pass
