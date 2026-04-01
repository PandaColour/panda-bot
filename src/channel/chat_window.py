"""PySide6 聊天窗口"""
import asyncio

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton
)
from PySide6.QtGui import QFont, QTextCursor

from src.agent.session import Session
from src.utils import get_logger

logger = get_logger(__name__)


class ChatWindow(QMainWindow):
    """聊天主窗口"""

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        self.setWindowTitle("Panda Bot")
        self.setGeometry(100, 100, 800, 600)

        # 中央控件
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 聊天记录显示区
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.chat_display, stretch=1)

        # 输入区域
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setFont(QFont("Microsoft YaHei", 10))
        self.input_field.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.input_field, stretch=1)

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

    def _send_message(self):
        """发送消息"""
        text = self.input_field.text().strip()
        if not text:
            return

        # 显示用户消息
        self._append_message("user", text)
        self.input_field.clear()

        # 推送到 session（asyncio queue 是线程安全的）
        asyncio.create_task(self.session.push_user_input(text))

    def _append_message(self, role: str, content: str):
        """添加消息到显示区"""
        prefix = "🧑 你" if role == "user" else "🤖 Panda"
        html = f"<p><b>{prefix}:</b></p><p>{content}</p><hr>"
        self.chat_display.append(html)
        # 滚动到底部
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)

    async def start_agent(self):
        """启动 agent（在 qasync 事件循环中运行）"""
        async def on_reply(content: str):
            self._append_message("assistant", content)

        self.session._reply_callback = on_reply
        await self.session.start_agent_loop()
