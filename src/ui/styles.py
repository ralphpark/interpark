DARK_THEME = """
    QMainWindow {
        background-color: #1a1a2e;
    }

    QLabel {
        color: #e0e0e0;
        font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
    }

    QLabel#titleLabel {
        font-size: 22px;
        font-weight: bold;
        color: #e94560;
        padding: 5px 0;
    }

    QLabel#sectionLabel {
        font-size: 13px;
        font-weight: bold;
        color: #8892b0;
        padding-top: 8px;
    }

    QPushButton {
        background-color: #0f3460;
        border: 1px solid #1a5276;
        border-radius: 8px;
        color: white;
        padding: 10px 24px;
        font-weight: bold;
        font-size: 13px;
        font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
    }

    QPushButton:hover {
        background-color: #1a5276;
        border: 1px solid #2980b9;
    }

    QPushButton:pressed {
        background-color: #0a2647;
    }

    QPushButton:disabled {
        background-color: #2c2c3e;
        color: #555;
        border: 1px solid #333;
    }

    QPushButton#startBtn {
        background-color: #e94560;
        border: 1px solid #c0392b;
        font-size: 15px;
        padding: 12px 32px;
    }

    QPushButton#startBtn:hover {
        background-color: #ff6b81;
    }

    QPushButton#startBtn:pressed {
        background-color: #c0392b;
    }

    QPushButton#stopBtn {
        background-color: #555;
        border: 1px solid #666;
    }

    QPushButton#stopBtn:hover {
        background-color: #e74c3c;
        border: 1px solid #c0392b;
    }

    QLineEdit, QDateEdit, QTimeEdit {
        background-color: #16213e;
        border: 1px solid #0f3460;
        border-radius: 6px;
        color: #e0e0e0;
        padding: 8px 12px;
        font-size: 14px;
        font-family: 'Consolas', 'D2Coding', monospace;
        selection-background-color: #e94560;
    }

    QLineEdit:focus, QDateEdit:focus, QTimeEdit:focus {
        border: 1px solid #e94560;
    }

    QDateEdit::drop-down, QTimeEdit::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 24px;
        border-left: 1px solid #0f3460;
    }

    QDateEdit::down-arrow, QTimeEdit::down-arrow {
        width: 12px;
        height: 12px;
    }

    QTextEdit#logPanel {
        background-color: #0d1117;
        color: #58a6ff;
        border: 1px solid #21262d;
        border-radius: 6px;
        padding: 8px;
        font-family: 'Consolas', 'D2Coding', 'Courier New', monospace;
        font-size: 12px;
        selection-background-color: #1f6feb;
    }

    QCheckBox {
        color: #e0e0e0;
        font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
        font-size: 13px;
        spacing: 8px;
    }

    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid #0f3460;
        background-color: #16213e;
    }

    QCheckBox::indicator:checked {
        background-color: #e94560;
        border: 1px solid #e94560;
    }

    QCheckBox::indicator:hover {
        border: 1px solid #e94560;
    }

    QStatusBar {
        background-color: #0d1117;
        color: #8892b0;
        font-family: 'Consolas', 'D2Coding', monospace;
        font-size: 11px;
        border-top: 1px solid #21262d;
    }

    QFrame#separator {
        background-color: #21262d;
        max-height: 1px;
    }
"""
