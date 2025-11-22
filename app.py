# app.py

import os
import sys

# Erlaubt Modulen, den Doku-Build zu erkennen (falls nötig)
IS_DOC_BUILD = os.environ.get("SPHINX_BUILD") == "1"

def main():
    # Lazy Imports: erst zur Laufzeit laden, NICHT beim Modul-Import
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("C-FUSE")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()