from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
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

from .backend import Backend, DemoBackend, OpenStackBackend, safe_error
from .models import CloudProfile, Desktop, LoginSession, UserError
from .remote import launch_rustdesk, validate_peer_id
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
        self.backend = backend or (DemoBackend() if demo else OpenStackBackend())
        self.settings = settings or SettingsStore()
        self.session: LoginSession | None = None
        self.desktops: list[Desktop] = []
        self._task: Task | None = None
        self._done: Callable | None = None
        self._busy = False
        self._fresh = False
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.setWindowTitle("OpenStack VDI" + (" — 데모" if demo else ""))
        self.resize(1120, 780)
        self.setMinimumSize(880, 720)
        self.setStyleSheet(STYLE)
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self._make_login_page()
        self._make_desktop_page()
        self.timer = QTimer(self)
        self.timer.setInterval(3000 if demo else 5000)
        self.timer.timeout.connect(self.refresh)
        self.statusBar().showMessage(self.settings.warning or "OpenStack 계정으로 로그인하세요.")
        if demo:
            QTimer.singleShot(0, self.login)

    def _make_login_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(48, 24, 48, 24)
        outer.addWidget(label("OpenStack VDI", "title"))
        outer.addWidget(label("내 데스크톱에 연결하세요", "subtitle"))
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        form = QFormLayout()
        form.setVerticalSpacing(8)
        profile = self.settings.profile()
        self.fields: dict[str, QLineEdit] = {}
        for key, title, value, placeholder in [
            ("auth_url", "인증 주소", profile.auth_url, "https://cloud.example:5000/v3"),
            ("username", "사용자", profile.username, "사용자 이름"),
            ("password", "비밀번호", "", "저장하지 않습니다"),
            ("project_name", "프로젝트", profile.project_name, "사용자에게 할당된 프로젝트"),
            ("user_domain", "사용자 도메인", profile.user_domain, "Default"),
            ("project_domain", "프로젝트 도메인", profile.project_domain, "Default"),
            ("region_name", "리전", profile.region_name, "비워두면 기본 리전"),
        ]:
            field = QLineEdit(value)
            field.setObjectName(key)
            field.setPlaceholderText(placeholder)
            if key == "password":
                field.setEchoMode(QLineEdit.EchoMode.Password)
                field.returnPressed.connect(self.login)
            self.fields[key] = field
            form.addRow(title, field)
        ca_row = QHBoxLayout()
        self.ca = QLineEdit(profile.ca_file)
        self.ca.setPlaceholderText("공인 인증서는 비워두세요")
        ca_row.addWidget(self.ca)
        browse = QPushButton("선택")
        browse.clicked.connect(self._choose_ca)
        ca_row.addWidget(browse)
        form.addRow("CA 인증서", ca_row)
        self.interface = QComboBox()
        self.interface.addItems(["public", "internal"])
        self.interface.setCurrentText(profile.interface)
        form.addRow("API 접속 경로", self.interface)
        layout.addLayout(form)
        self.login_error = label("", "error")
        self.login_error.hide()
        layout.addWidget(self.login_error)
        self.login_button = QPushButton("로그인")
        self.login_button.setObjectName("primary")
        self.login_button.clicked.connect(self.login)
        layout.addWidget(self.login_button)
        outer.addWidget(card)
        outer.addWidget(
            label(
                "접속 정보만 저장합니다. 비밀번호와 인증 토큰은 파일에 저장하지 않습니다.", "muted"
            )
        )
        outer.addStretch()
        self.pages.addWidget(page)

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
        self.settings_button = QPushButton("RustDesk 설정")
        self.settings_button.clicked.connect(self.configure_rustdesk)
        header.addWidget(self.settings_button)
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
        self.table.setHorizontalHeaderLabels(["데스크톱", "전원 상태", "IP 주소", "RustDesk ID"])
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
        for action, title in [("start", "켜기"), ("reboot", "재부팅"), ("stop", "전원 정지")]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, action=action: self.power(action))
            self.buttons[action] = button
            actions.addWidget(button)
        self.peer_button = QPushButton("연결 ID 설정")
        self.peer_button.clicked.connect(self.configure_peer)
        actions.addWidget(self.peer_button)
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
            lambda session: self._logged_in(session, profile),
            "로그인 중…",
        )

    def _logged_in(self, session: LoginSession, profile: CloudProfile):
        self.session = session
        if not self.demo:
            try:
                self.settings.save_profile(profile)
            except UserError as error:
                self.statusBar().showMessage(str(error))
        self.account.setText(f"{session.username}  /  {session.project_name}")
        self.pages.setCurrentIndex(1)
        self.timer.start()
        self.refresh()

    def logout(self):
        if self._busy:
            return
        self.timer.stop()
        self._run(self.backend.close, self._logged_out, "로그아웃 중…")

    def _logged_out(self, _):
        self.session = None
        self.desktops = []
        self.table.setRowCount(0)
        self._fresh = False
        self.pages.setCurrentIndex(0)
        self.statusBar().showMessage("로그아웃했습니다. 이미 열린 RustDesk 연결은 별도로 닫으세요.")

    def _run(self, operation: Callable, done: Callable, message: str):
        if self._busy:
            return
        self._busy = True
        self._done = done
        self._task = Task(operation)
        self._task.signals.complete.connect(self._finished)
        self._update_controls()
        self.statusBar().showMessage(message)
        self.pool.start(self._task)

    @Slot(object, object)
    def _finished(self, result, error):
        callback = self._done
        self._busy = False
        self._task = None
        self._done = None
        if error:
            self._fresh = False
            self.statusBar().showMessage(error)
            if self.pages.currentIndex() == 0:
                self.login_error.setText(error)
                self.login_error.show()
            else:
                self.notice.setText(error)
                self.notice.setObjectName("error")
                self.notice.style().unpolish(self.notice)
                self.notice.style().polish(self.notice)
        elif callback:
            callback(result)
        self._update_controls()

    def refresh(self):
        if self.session is None or self._busy:
            return
        self._run(self.backend.list_desktops, self._show_desktops, "데스크톱 상태 확인 중…")

    def _show_desktops(self, desktops: list[Desktop]):
        selected = self.selected()
        selected_id = selected.id if selected else None
        self.desktops = desktops
        self._fresh = True
        self.table.setRowCount(0)
        for row, desktop in enumerate(desktops):
            self.table.insertRow(row)
            status = (
                "작업 중"
                if desktop.task_state
                else {
                    "ACTIVE": "켜짐",
                    "SHUTOFF": "꺼짐",
                    "BUILD": "생성 중",
                    "ERROR": "오류",
                }.get(desktop.status, desktop.status)
            )
            peer = self.settings.peer_id(self.session.scope_key, desktop.id)
            for column, value in enumerate(
                (desktop.name, status, ", ".join(desktop.addresses) or "—", peer or "미등록")
            ):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setForeground(
                        QColor("#86efac" if desktop.allows("connect") else "#aabbd4")
                    )
                item.setToolTip(value)
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 64)
        if desktops:
            row = next((i for i, desktop in enumerate(desktops) if desktop.id == selected_id), 0)
            self.table.selectRow(row)
        self.count.setText(
            f"데스크톱 {len(desktops)}대"
            if desktops
            else "이 프로젝트에 VM이 없습니다. 관리자에게 테스트 VM 할당을 요청하세요."
        )
        self.notice.setObjectName("notice")
        self.notice.setText(
            "데모 모드 · 실제 VM과 연결되지 않습니다. 전원 버튼으로 동작을 살펴보세요."
            if self.demo
            else "전원을 켠 뒤 Windows와 RustDesk가 시작될 때까지 기다리세요."
        )
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)
        self.statusBar().showMessage("최신 상태를 확인했습니다.")
        self._selection_changed()

    def selected(self) -> Desktop | None:
        row = self.table.currentRow()
        return self.desktops[row] if 0 <= row < len(self.desktops) else None

    def _selection_changed(self):
        desktop = self.selected()
        self.details.setText(f"VM ID  {desktop.id}" if desktop else "데스크톱을 선택하세요.")
        self._update_controls()

    def _update_controls(self):
        self.login_button.setEnabled(not self._busy)
        self.login_button.setText("로그인 중…" if self._busy and self.session is None else "로그인")
        if not hasattr(self, "table"):
            return
        desktop = self.selected()
        available = desktop is not None and not self._busy and self._fresh
        for action, button in self.buttons.items():
            button.setEnabled(bool(available and desktop.allows(action)))
        self.connect_button.setEnabled(bool(available and desktop.allows("connect")))
        self.peer_button.setEnabled(bool(available))
        self.refresh_button.setEnabled(not self._busy)
        self.logout_button.setEnabled(not self._busy)
        self.settings_button.setEnabled(not self._busy)

    def power(self, action: str):
        desktop = self.selected()
        if self._busy or not self._fresh or desktop is None or not desktop.allows(action):
            return
        title = {"start": "켜기", "stop": "전원 정지", "reboot": "재부팅"}[action]
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
        self._run(
            lambda: self.backend.power(desktop.id, action),
            lambda _: self.refresh(),
            f"{title} 요청 중…",
        )

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
            self._busy
            or not self._fresh
            or self.session is None
            or desktop is None
            or not desktop.allows("connect")
        ):
            return
        if self.demo:
            self.statusBar().showMessage("데모 모드에서는 RustDesk를 실행하지 않습니다.")
            return
        peer = self.settings.peer_id(self.session.scope_key, desktop.id)
        if not peer:
            if not self.configure_peer():
                return
            peer = self.settings.peer_id(self.session.scope_key, desktop.id)
        try:
            launch_rustdesk(peer, self.settings.rustdesk_path)
            self.statusBar().showMessage(
                "RustDesk 접속 창을 열었습니다. 인증은 RustDesk에서 진행하세요."
            )
        except UserError as error:
            QMessageBox.warning(self, "원격 접속", str(error))

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
            self.statusBar().showMessage("진행 중인 요청이 끝난 뒤 창을 닫아주세요.")
            return
        self.timer.stop()
        self.backend.close()
        event.accept()


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenStack VDI native launcher")
    parser.add_argument("--demo", action="store_true", help="클라우드 연결 없이 데모 UI 실행")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("OpenStack VDI")
    app.setOrganizationName("OpenStackVDI")
    window = MainWindow(demo=args.demo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
