from PySide6.QtWidgets import QMessageBox


def confirm(parent, title, text):
    dialog = QMessageBox(QMessageBox.Icon.Question, title, text, parent=parent)
    accept = dialog.addButton("확인", QMessageBox.ButtonRole.AcceptRole)
    cancel = dialog.addButton("취소", QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(cancel)
    dialog.setEscapeButton(cancel)
    dialog.exec()
    return dialog.clickedButton() is accept
