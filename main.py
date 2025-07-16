import sys
from PyQt5.QtWidgets import QApplication
from venv_manager_ui import VenvManagerWindow
from package_manager_ui import PackageManagerDialog
from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QIcon
import os


def main():
    app = QApplication(sys.argv)
    
    # 设置应用图标
    icon_path = os.path.join(os.path.dirname(__file__), 'icons', 'app.ico')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    window = VenvManagerWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main() 