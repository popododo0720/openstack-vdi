from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import credentials
from .backend import Backend, DemoBackend, OpenStackBackend, safe_error
from .broker_client import BrokerBackend
from .connection_flow import ConnectIntent
from .models import CloudProfile, Desktop, LoginSession, UserError
from .native_session import NativeSession, focus_peer
from .remote import validate_peer_id
from .settings import SettingsStore

STYLE = """
QWidget { font-family: 'Segoe UI', 'Noto Sans CJK KR', sans-serif; font-size: 13px;
          color: #dce5f5; background: #111827; }
QMainWindow { background: #111827; }
QLabel#title { font-size: 26px; font-weight: 700; color: #f7faff; }
QLabel#subtitle, QLabel#muted { color: #9aabc4; }
QLabel#notice { background: #1b2f48; color: #bfdbfe; padding: 12px; border-radius: 8px; }
QLabel#error { background: #41242c; color: #fecaca; padding: 12px; border-radius: 8px; }
QFrame#card { background: #182235; border: 1px solid #2d3b51; border-radius: 12px; }
QFrame#card QLabel { background: transparent; }
QLineEdit, QComboBox { background: #0e1728; border: 1px solid #40516c;
                     padding: 9px; border-radius: 6px; selection-background-color: #2563eb; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #60a5fa; }
QPushButton { background: #25354e; border: 1px solid #425675; border-radius: 6px;
              padding: 10px 17px; font-weight: 600; }
QPushButton:hover { background: #334b6b; }
QPushButton#primary { background: #2563eb; border-color: #3b82f6; color: white; }
QPushButton#primary:hover { background: #1d4ed8; }
QPushButton:disabled { background: #1a2538; color: #607089; border-color: #29374d; }
QTableWidget { background: #182235; alternate-background-color: #1b283d;
               border: 1px solid #2d3b51; border-radius: 8px; gridline-color: #2d3b51; }
QTableWidget::item { padding: 12px; }
QTableWidget::item:selected { background: #254574; color: white; }
QHeaderView::section { background: #202e45; color: #aabbd4; padding: 12px; border: none; }
QStatusBar { color: #9aabc4; background: #0d1524; }
QDialog { background: #111827; }
"""


def label(text: str, name: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


class TaskSignals(QObject):
    complete = Signal(object, object)


class Task(QRunnable):
    def __init__(self, operation: Callable):
        super().__init__()
        self.operation = operation
        self.signals = TaskSignals()

    def run(self):
        try:
            result = self.operation()
        except Exception as error:
            self.signals.complete.emit(None, safe_error(error))
        else:
            self.signals.complete.emit(result, None)
        finally:
            self.operation = None  # Release closures which may temporarily hold login credentials.


class PeerDialog(QDialog):
    def __init__(self, desktop: Desktop, peer_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RustDesk 연결 설정")
        self.resize(460, 220)
        layout = QVBoxLayout(self)
        layout.addWidget(label(desktop.name, "title"))
        layout.addWidget(label("VM 안에서 RustDesk를 열어 표시된 ID를 입력하세요.", "muted"))
        self.peer = QLineEdit(peer_id)
        self.peer.setPlaceholderText("예: 123 456 789")
        layout.addWidget(self.peer)
        layout.addWidget(
            label("접속 비밀번호는 RustDesk 창에서 입력하며, 이 앱에 저장하지 않습니다.")
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        try:
            self.peer.setText(validate_peer_id(self.peer.text()))
        except UserError as error:
            QMessageBox.warning(self, "ID 확인", str(error))
            return
        super().accept()


class MainWindow(QMainWindow):
    def __init__(
        self,
        backend: Backend | None = None,
        settings: SettingsStore | None = None,
        demo: bool = False,
    ):
        super().__init__()
        self.demo = demo
        self.settings = settings or SettingsStore()
        self._provided_backend = backend
        self.backend = backend or (
            DemoBackend()
            if demo
            else (BrokerBackend() if self.settings.profile().broker_url else OpenStackBackend())
        )
        self.remote = NativeSession()
        self.intent = None
        self._remote_id = ""
        self._background = False
        self._queued = None
        self._last_refresh = 0.0
        self._auto_retried = False
        self._connect_generation = 0
        self._opening = False
        self.session: LoginSession | None = None
        self.desktops: list[Desktop] = []
        self._task: Task | None = None
        self._done: Callable | None = None
        self._busy = False
        self._fresh = False
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.setWindowTitle("OpenStack VDI" + (" — 데모" if demo else ""))
        self.resize(1000, 680)
        self.setMinimumSize(760, 560)
        self.setStyleSheet(STYLE)
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self._make_login_page()
        self._make_desktop_page()
        self.timer = QTimer(self)
        self.timer.setInterval(3000 if demo else 5000)
        self.timer.timeout.connect(self.refresh)
        self.remote_timer = QTimer(self)
        self.remote_timer.setInterval(1000)
        self.remote_timer.timeout.connect(self._poll_remote)
        self.remote_timer.start()
        self.statusBar().showMessage(self.settings.warning or "OpenStack 계정으로 로그인하세요.")
        if demo:
            QTimer.singleShot(0, self.login)

    def _make_login_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(48, 24, 48, 24)
        outer.addWidget(label("OpenStack VDI", "title"))
        outer.addWidget(label("회사 계정으로 내 데스크톱에 접속하세요", "subtitle"))
        profile = self.settings.profile()
        self.fields = {}
        form = QFormLayout()
        for key, title, value in [
            ("username", "계정", profile.username),
            ("password", "비밀번호", ""),
        ]:
            field = QLineEdit(value)
            field.setObjectName(key)
            if key == "password":
                field.setEchoMode(QLineEdit.EchoMode.Password)
                field.returnPressed.connect(self.login)
            self.fields[key] = field
            form.addRow(title, field)
        outer.addLayout(form)
        self.remember = QCheckBox("이 Windows 계정에 로그인 정보 저장")
        self.remember.setEnabled(os.name == "nt" and not self.demo)
        self.remember.setToolTip(
            "Windows 자격 증명 관리자에 저장합니다. 공유 PC에서는 선택하지 마세요."
        )
        outer.addWidget(self.remember)
        self.advanced = QWidget()
        advanced = QFormLayout(self.advanced)
        for key, title, value in [
            ("broker_url", "VDI 서버", profile.broker_url),
            ("auth_url", "직접 연결 인증 주소", profile.auth_url),
            ("project_name", "직접 연결 프로젝트", profile.project_name),
            ("user_domain", "사용자 도메인", profile.user_domain),
            ("project_domain", "프로젝트 도메인", profile.project_domain),
            ("region_name", "리전", profile.region_name),
        ]:
            field = QLineEdit(value)
            self.fields[key] = field
            advanced.addRow(title, field)
        self.ca = QLineEdit(profile.ca_file)
        ca_row = QHBoxLayout()
        ca_row.addWidget(self.ca)
        browse = QPushButton("인증서 선택")
        browse.clicked.connect(self._choose_ca)
        ca_row.addWidget(browse)
        advanced.addRow("CA 인증서", ca_row)
        self.interface = QComboBox()
        self.interface.addItems(["public", "internal"])
        self.interface.setCurrentText(profile.interface)
        advanced.addRow("직접 연결 경로", self.interface)
        toggle = QPushButton("연결 설정")
        toggle.setCheckable(True)
        toggle.toggled.connect(self.advanced.setVisible)
        outer.addWidget(toggle)
        outer.addWidget(self.advanced)
        self.advanced.hide()
        self.login_error = label("", "error")
        self.login_error.hide()
        outer.addWidget(self.login_error)
        self.login_button = QPushButton("로그인")
        self.login_button.setObjectName("primary")
        self.login_button.clicked.connect(self.login)
        outer.addWidget(self.login_button)
        outer.addWidget(
            label(
                "RustDesk 암호는 첫 연결 때 ‘비밀번호 기억’을 선택하세요.\n"
                "Windows 잠금은 Windows 계정으로 해제합니다.",
                "muted",
            )
        )
        outer.addStretch()
        self.pages.addWidget(page)
        saved = credentials.read(profile)
        if saved:
            self.fields["password"].setText(saved)
            self.remember.setChecked(True)
        self.fields["username"].textChanged.connect(lambda _: self.fields["password"].clear())

    def _make_desktop_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("내 데스크톱", "title"))
        self.account = label("", "subtitle")
        titles.addWidget(self.account)
        header.addLayout(titles)
        header.addStretch()
        self.settings_button = QPushButton("연결 설정")
        self.settings_button.clicked.connect(self.configure_rustdesk)
        header.addWidget(self.settings_button)
        self.about_button = QPushButton("앱 정보 / 업데이트")
        self.about_button.clicked.connect(self.about)
        header.addWidget(self.about_button)
        self.logout_button = QPushButton("로그아웃")
        self.logout_button.clicked.connect(self.logout)
        header.addWidget(self.logout_button)
        layout.addLayout(header)
        self.notice = label(
            "데모 모드 · 표시된 VM과 전원 작업은 시뮬레이션입니다. 실제 연결은 실행하지 않습니다."
            if self.demo
            else "VM을 선택한 뒤 접속하세요. 처음 접속할 때 RustDesk ID를 등록합니다.",
            "notice",
        )
        layout.addWidget(self.notice)
        row = QHBoxLayout()
        self.count = label("데스크톱을 불러오는 중…", "muted")
        row.addWidget(self.count)
        row.addStretch()
        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["내 PC", "상태", "IP 주소", "RustDesk ID"])
        self.table.setColumnHidden(2, True)
        self.table.setColumnHidden(3, True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(lambda _: self.connect_desktop())
        layout.addWidget(self.table, 1)
        self.details = label("데스크톱을 선택하세요.", "muted")
        layout.addWidget(self.details)
        actions = QHBoxLayout()
        self.buttons: dict[str, QPushButton] = {}
        for action, title in [("start", "켜기"), ("reboot", "재부팅 후 접속"), ("stop", "PC 종료")]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, action=action: self.power(action))
            self.buttons[action] = button
            actions.addWidget(button)
        self.peer_button = QPushButton("연결 ID 설정")
        self.peer_button.clicked.connect(self.configure_peer)
        actions.addWidget(self.peer_button)
        self.cancel_button = QPushButton("접속 취소")
        self.cancel_button.clicked.connect(self.cancel_connect)
        actions.addWidget(self.cancel_button)
        self.disconnect_button = QPushButton("연결 창 닫기")
        self.disconnect_button.clicked.connect(self.disconnect)
        actions.addWidget(self.disconnect_button)
        actions.addStretch()
        self.connect_button = QPushButton("데스크톱 접속")
        self.connect_button.setObjectName("primary")
        self.connect_button.clicked.connect(self.connect_desktop)
        actions.addWidget(self.connect_button)
        layout.addLayout(actions)
        layout.addWidget(
            label(
                "원격 창을 닫으면 연결만 해제됩니다. 전원 정지는 Windows 작업을 종료합니다.",
                "muted",
            )
        )
        self.pages.addWidget(page)
        self._update_controls()

    def _choose_ca(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "OpenStack CA 인증서 선택",
            "",
            "인증서 (*.crt *.pem);;모든 파일 (*)",
        )
        if filename:
            self.ca.setText(filename)

    def _profile(self) -> CloudProfile:
        values = {
            key: field.text().strip() for key, field in self.fields.items() if key != "password"
        }
        return CloudProfile(
            **values, ca_file=self.ca.text().strip(), interface=self.interface.currentText()
        )

    def login(self):
        if self._busy:
            return
        profile = self._profile()
        password = self.fields["password"].text()
        if not self.demo and self._provided_backend is None:
            self.backend = BrokerBackend() if profile.broker_url else OpenStackBackend()
        if not self.demo:
            try:
                profile.validate()
                if not password:
                    raise UserError("비밀번호를 입력하세요.")
            except UserError as error:
                self.login_error.setText(str(error))
                self.login_error.show()
                return
        self.login_error.hide()
        self.fields["password"].clear()
        self._run(
            lambda: self.backend.login(profile, password),
            lambda session: self._logged_in(session, profile, password),
            "로그인 중…",
        )

    def _logged_in(self, session: LoginSession, profile: CloudProfile, password=""):
        self.session = session
        if not self.demo:
            try:
                self.settings.save_profile(profile)
                if self.remember.isChecked():
                    credentials.save(profile, password)
                else:
                    credentials.forget(profile)
            except UserError as error:
                self.statusBar().showMessage(str(error))
        self.account.setText(f"{session.username} 님")
        self.peer_button.setVisible(not isinstance(self.backend, BrokerBackend))
        self.settings_button.setVisible(not isinstance(self.backend, BrokerBackend))
        self.pages.setCurrentIndex(1)
        self.timer.start()
        self.refresh()

    def logout(self):
        if self._foreground_busy():
            return
        if (
            self.remote.peer
            and QMessageBox.question(
                self,
                "로그아웃",
                "이 앱에서 연 원격 창을 닫고 로그아웃할까요? 업무용 PC는 계속 켜져 있습니다.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._connect_generation += 1
        self._opening = False
        self.intent = None
        self._queued = None
        self.remote.close()
        self.timer.stop()
        credentials.forget(self.settings.profile())
        self.remember.setChecked(False)
        self._run(self.backend.close, self._logged_out, "로그아웃 중…")

    def _logged_out(self, _):
        self.session = None
        self.desktops = []
        self.table.setRowCount(0)
        self._fresh = False
        self.pages.setCurrentIndex(0)
        self.statusBar().showMessage("로그아웃했습니다. 저장한 앱 로그인 정보도 삭제했습니다.")

    def _foreground_busy(self):
        return (self._busy and not self._background) or self._queued is not None

    def _run(self, operation: Callable, done: Callable, message: str, background=False):
        if self._busy:
            if self._background and not background and self._queued is None:
                self._queued = (operation, done, message)
                self._update_controls()
            return
        self._busy = True
        self._background = background
        self._done = done
        self._task = Task(operation)
        self._task.signals.complete.connect(self._finished)
        self._update_controls()
        if not background:
            self.statusBar().showMessage(message)
        self.pool.start(self._task)

    @Slot(object, object)
    def _finished(self, result, error):
        callback, background = self._done, self._background
        queued = self._queued
        self._busy = self._background = False
        self._task = self._done = None
        if error:
            self._fresh = False
            if not background:
                self.intent = None
            self.statusBar().showMessage(error)
            if self.pages.currentIndex() == 0:
                self.login_error.setText(error)
                self.login_error.show()
            else:
                self.notice.setText(error + "  새로고침으로 다시 시도할 수 있습니다.")
        elif callback:
            try:
                callback(result)
            except Exception as callback_error:
                self._opening = False
                self.intent = None
                self.notice.setText(safe_error(callback_error))
        self._queued = None
        if queued:
            self._run(*queued)
        self._update_controls()

    def refresh(self):
        if self.session is None or self._busy:
            return
        self._run(self.backend.list_desktops, self._show_desktops, "", background=True)

    def _show_desktops(self, desktops: list[Desktop]):
        selected = self.selected()
        selected_id = selected.id if selected else None
        scroll = self.table.verticalScrollBar().value()
        self.desktops = desktops
        self._fresh = True
        self._last_refresh = time.monotonic()
        self.table.blockSignals(True)
        self.table.setRowCount(len(desktops))
        for row, desktop in enumerate(desktops):
            if desktop.task_state:
                status = (
                    "종료 중"
                    if "off" in desktop.task_state or desktop.task_state == "stop"
                    else "부팅 / 재시작 중"
                )
            elif desktop.status == "ACTIVE":
                status = (
                    "접속 준비됨"
                    if desktop.ready
                    else (desktop.readiness_message or "켜짐 · 접속 상태 미확인")
                )
            else:
                status = {
                    "SHUTOFF": "꺼짐 · 접속하면 자동으로 켜집니다",
                    "BUILD": "준비 중",
                    "ERROR": "PC 오류 · 관리자에게 문의",
                }.get(desktop.status, desktop.status)
            if desktop.id == self._remote_id and self.remote.peer:
                status = {
                    "connected": "연결됨",
                    "opening": "접속 창 열림 · 인증 대기",
                    "authenticating": "화면 수신 대기",
                    "disconnected": "연결 끊김",
                }.get(self.remote.state, status)
            peer = desktop.peer_id or self.settings.peer_id(self.session.scope_key, desktop.id)
            for column, value in enumerate(
                (desktop.name, status, ", ".join(desktop.addresses), peer)
            ):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setForeground(QColor("#86efac" if desktop.ready else "#aabbd4"))
                item.setToolTip(value)
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 64)
        if desktops:
            self.table.selectRow(
                next((i for i, d in enumerate(desktops) if d.id == selected_id), 0)
            )
        self.table.verticalScrollBar().setValue(scroll)
        self.table.blockSignals(False)
        self.count.setText(
            f"내 PC {len(desktops)}대"
            if desktops
            else "배정된 PC가 없습니다. 관리자에게 데스크톱 배정을 요청하세요."
        )
        if not self.intent:
            self.notice.setText(
                "데모 모드 · 실제 원격 연결은 실행하지 않습니다."
                if self.demo
                else "PC를 선택하고 접속하세요. 꺼져 있으면 자동으로 켠 뒤 연결합니다."
            )
        self._selection_changed()
        self._advance_connect()

    def selected(self) -> Desktop | None:
        row = self.table.currentRow()
        return self.desktops[row] if 0 <= row < len(self.desktops) else None

    def _selection_changed(self):
        desktop = self.selected()
        self.details.setText(desktop.name if desktop else "데스크톱을 선택하세요.")
        self._update_controls()

    def _update_controls(self):
        busy = self._foreground_busy()
        self.login_button.setEnabled(not busy)
        self.login_button.setText("로그인 중…" if busy and self.session is None else "로그인")
        if not hasattr(self, "table"):
            return
        desktop = self.selected()
        available = desktop is not None and not busy and self._fresh
        for action, button in self.buttons.items():
            button.setEnabled(bool(available and not self.intent and desktop.allows(action)))
        self.connect_button.setEnabled(
            bool(available and not self.intent and desktop.allows("connect"))
        )
        self.connect_button.setText(
            "켜고 접속" if desktop and desktop.status == "SHUTOFF" else "데스크톱 접속"
        )
        self.peer_button.setEnabled(bool(available))
        self.refresh_button.setEnabled(not self._busy)
        self.logout_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.cancel_button.setVisible(self.intent is not None or self._opening)
        self.disconnect_button.setEnabled(bool(self.remote.peer))

    def power(self, action: str):
        desktop = self.selected()
        if (
            self._foreground_busy()
            or not self._fresh
            or desktop is None
            or not desktop.allows(action)
        ):
            return
        title = {"start": "켜기", "stop": "PC 종료", "reboot": "재부팅 후 접속"}[action]
        if action != "start":
            answer = QMessageBox.question(
                self,
                title,
                f"{desktop.name}을(를) {title}할까요?\n저장하지 않은 작업이 사라질 수 있습니다.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if action == "reboot" and isinstance(self.backend, BrokerBackend):
            self.intent = ConnectIntent.begin(desktop, reboot=True)
            self.notice.setText("재부팅을 요청합니다. Windows가 준비되면 자동으로 다시 접속합니다.")

        def accepted(_):
            if self._remote_id == desktop.id and action in ("stop", "reboot"):
                self.remote.close()
            self.refresh()

        self._run(lambda: self.backend.power(desktop.id, action), accepted, f"{title} 요청 중…")

    def configure_peer(self) -> bool:
        desktop = self.selected()
        if desktop is None or self.session is None:
            return False
        dialog = PeerDialog(
            desktop, self.settings.peer_id(self.session.scope_key, desktop.id), self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            self.settings.save_peer_id(self.session.scope_key, desktop.id, dialog.peer.text())
        except UserError as error:
            QMessageBox.warning(self, "설정 저장", str(error))
            return False
        self.table.item(self.table.currentRow(), 3).setText(dialog.peer.text())
        return True

    def configure_rustdesk(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "RustDesk 실행 파일 선택",
            self.settings.rustdesk_path,
            "실행 파일 (*.exe *.AppImage);;모든 파일 (*)",
        )
        if filename:
            try:
                self.settings.save_rustdesk_path(filename)
                self.statusBar().showMessage("RustDesk 실행 파일을 저장했습니다.")
            except UserError as error:
                QMessageBox.warning(self, "설정 저장", str(error))

    def connect_desktop(self):
        desktop = self.selected()
        if (
            self._foreground_busy()
            or not self._fresh
            or not self.session
            or not desktop
            or not desktop.allows("connect")
            or self.intent
        ):
            return
        if self.demo:
            self.statusBar().showMessage("데모 모드에서는 RustDesk를 실행하지 않습니다.")
            return
        peer = desktop.peer_id or self.settings.peer_id(self.session.scope_key, desktop.id)
        if self.remote.state != "disconnected" and peer and focus_peer(peer):
            self.statusBar().showMessage("열려 있는 원격 창으로 이동했습니다.")
            return
        if self.remote.peer:
            if (
                self._remote_id != desktop.id
                and QMessageBox.question(
                    self,
                    "PC 전환",
                    "선택한 PC로 연결을 바꿀까요? 기존 PC의 작업은 유지됩니다.",
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            self.remote.close()
        if not peer and not isinstance(self.backend, BrokerBackend):
            if not self.configure_peer():
                return
        self._auto_retried = False
        self.intent = ConnectIntent.begin(desktop)
        self._advance_connect()

    def _advance_connect(self):
        if self.intent is None or self._foreground_busy():
            return
        desktop = next((d for d in self.desktops if d.id == self.intent.desktop_id), None)
        step = self.intent.step(desktop)
        if step in ("timeout", "missing", "error"):
            self.intent = None
            self.notice.setText(
                {
                    "timeout": "접속 준비 시간이 초과됐습니다. PC 상태를 확인하고 다시 접속하세요.",
                    "missing": "PC 배정이 변경됐습니다. 관리자에게 문의하세요.",
                    "error": "PC에 오류가 있습니다. 관리자에게 문의하세요.",
                }[step]
            )
        elif step == "start":
            self.notice.setText("PC를 켜고 있습니다. Windows가 준비되면 자동으로 연결합니다.")
            self._run(
                lambda: self.backend.power(desktop.id, "start"),
                lambda _: self.refresh(),
                "PC 켜는 중…",
            )
        elif step == "wait":
            seconds = max(0, int(self.intent.deadline - time.monotonic()))
            self.notice.setText(
                f"{desktop.name} 접속 준비 중 · 최대 {seconds}초 남음. "
                "취소해도 PC 전원은 유지됩니다."
            )
        elif step == "connect":
            self.intent = None
            self._opening = True
            generation = self._connect_generation

            def open_peer(peer):
                self._opening = False
                if generation != self._connect_generation or self.session is None:
                    return
                self.remote.open(peer, self.settings.rustdesk_path)
                self._remote_id = desktop.id
                self.notice.setText(
                    "원격 접속 창을 열었습니다. 첫 연결에는 RustDesk 암호를 입력하세요."
                )

            if isinstance(self.backend, BrokerBackend):
                self._run(
                    lambda: self.backend.connection_peer(desktop.id),
                    open_peer,
                    "접속 권한 확인 중…",
                )
            else:
                try:
                    open_peer(
                        desktop.peer_id or self.settings.peer_id(self.session.scope_key, desktop.id)
                    )
                except UserError as error:
                    self.notice.setText(str(error))
        self._update_controls()

    def cancel_connect(self):
        self._connect_generation += 1
        self._opening = False
        self.intent = None
        self.notice.setText("자동 접속을 취소했습니다. 이미 요청한 전원 작업은 계속 진행됩니다.")
        self._update_controls()

    def disconnect(self):
        self.cancel_connect()
        self.remote.close()
        self.notice.setText("원격 창을 닫았습니다. 업무용 PC와 실행 중인 프로그램은 유지됩니다.")
        self._update_controls()

    def _poll_remote(self):
        state = self.remote.poll()
        if self.session and self._last_refresh and time.monotonic() - self._last_refresh > 30:
            self._fresh = False
        if (
            state == "disconnected"
            and self.remote.was_connected
            and not self.intent
            and not self._auto_retried
            and isinstance(self.backend, BrokerBackend)
        ):
            desktop = next((d for d in self.desktops if d.id == self._remote_id), None)
            if desktop and desktop.ready is False:
                self._auto_retried = True
                self.remote.close()
                self.intent = ConnectIntent.begin(desktop)
        if self.intent and time.monotonic() >= self.intent.deadline:
            self.intent = None
            self.notice.setText(
                "접속 대기 시간이 초과됐습니다. 네트워크와 PC 상태를 확인하고 다시 시도하세요."
            )
        self._update_controls()

    def about(self):
        from .updates import show_update_dialog

        show_update_dialog(self)

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
            self.statusBar().showMessage("진행 중인 요청이 끝난 뒤 창을 닫아주세요.")
            return
        if self.remote.peer:
            answer = QMessageBox.question(
                self,
                "앱 종료",
                "원격 연결 창도 닫고 앱을 종료할까요? 업무용 PC는 계속 켜져 있습니다.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.intent = None
        self.remote.close()
        self.timer.stop()
        self.remote_timer.stop()
        self.backend.close()
        event.accept()


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenStack VDI native launcher")
    parser.add_argument("--demo", action="store_true", help="클라우드 연결 없이 데모 UI 실행")
    parser.add_argument("--check-package", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check_package:
        from .runtime_check import check_package_runtime

        try:
            check_package_runtime()
        except Exception:
            return 1
        return 0
    app = QApplication(sys.argv[:1])
    app.setApplicationName("OpenStack VDI")
    app.setOrganizationName("OpenStackVDI")
    window = MainWindow(demo=args.demo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
