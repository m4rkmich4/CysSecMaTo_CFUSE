# Filename: ui/control_mapping_view.py
# Combined Control Mapping View with 1:N and N:M subviews and stylized Header

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget, QFrame, QButtonGroup
)
from PySide6.QtCore import Qt

from ui.control_mapping_1n_view import ControlMapping1NView
from ui.control_mapping_mn_view import ControlMappingMNView


class ControlMappingView(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("ControlMappingMainView")
        self.setMinimumWidth(1000)

        # --- Header Frame mit Buttons ---
        header = QFrame()
        header.setFrameShape(QFrame.NoFrame)
        # padding oben/unten, Hintergrundband
        header.setStyleSheet(
            "QFrame { background: #333; padding: 2px 0; }"
        )
        header_layout = QHBoxLayout(header)
        # Abstände links/rechts für optische Trennung
        header_layout.setContentsMargins(20, 0, 20, 0)
        header_layout.setSpacing(20)

        # 1:N und N:M Schalter
        btn_1n = QPushButton("1:N")
        btn_mn = QPushButton("N:M")
        for b in (btn_1n, btn_mn):
            b.setCheckable(True)
            # 30% größere Buttons: Breite und Höhe anpassen
            b.setMinimumWidth(int(80 * 1.3))     # vorher 80 -> jetzt 104
            b.setMinimumHeight(int(30 * 1.3))    # vorher ca. 30 -> jetzt 39
            # Hover- und Checked-Effekte, leicht größere Polsterung
            b.setStyleSheet(
                "QPushButton {"
                "  background: #555;"
                "  color: #fff;"
                "  border: none;"
                "  border-radius: 4px;"
                "  padding: 8px 16px;"  # Padding leicht erhöht
                "}"  
                "QPushButton:hover { background: #666; }"  
                "QPushButton:checked { background: #888; }"
            )

        # exklusive Gruppe, damit nur einer aktiv ist
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        grp.addButton(btn_1n)
        grp.addButton(btn_mn)
        btn_1n.setChecked(True)  # Default-Auswahl

        # Buttons zentriert platzieren
        header_layout.addStretch()
        header_layout.addWidget(btn_1n, alignment=Qt.AlignCenter)
        header_layout.addWidget(btn_mn, alignment=Qt.AlignCenter)
        header_layout.addStretch()

        # --- Subviews ---
        self.views = QStackedWidget()
        self.view_1n = ControlMapping1NView()
        self.view_mn = ControlMappingMNView()
        self.views.addWidget(self.view_1n)
        self.views.addWidget(self.view_mn)

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        # Header oben
        main_layout.addWidget(header)
        # darunter die Views
        main_layout.addWidget(self.views)

        # --- Connect Buttons zum Umschalten ---
        btn_1n.clicked.connect(lambda: self.views.setCurrentWidget(self.view_1n))
        btn_mn.clicked.connect(lambda: self.views.setCurrentWidget(self.view_mn))

        # Default: 1:N view
        self.views.setCurrentWidget(self.view_1n)
