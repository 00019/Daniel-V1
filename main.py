import sys
import os
from PySide6.QtWidgets import QApplication
from ui.home_window import HomeWindow

if __name__ == "__main__":
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(project_root)
    app = QApplication(sys.argv)
    window = HomeWindow(project_root)
    window.show()
    sys.exit(app.exec())
