# ui/sidebar.py
"""
Defines the sidebar component of the application.
(Rest of the docstring as before)
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PySide6.QtCore import Signal, Qt

class Sidebar(QWidget):
    """
    A widget that serves as a navigation bar on the left edge.
    (Rest of the docstring as before)
    """

    view_changed = Signal(int)

    def __init__(self):
        """
        Initializes the sidebar, creates the layout, and adds the
        navigation buttons for the different views.
        """
        super().__init__()
        self.setObjectName("Sidebar")  # For CSS styling
        self.buttons = []              # Referenced buttons
        self.current_index = 0         # Active view (Index 0 is now Standard Comparison)

        # === Define Layout ===
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(10) # Keeps the desired spacing
        self.layout.setContentsMargins(10, 20, 10, 10)

        # === Labels for the navigation buttons (NEW ORDER AND NAMES) ===
        labels = [
            "Comparison",          # Index 0
            "Context Retrieval",   # Index 1
            "Catalog Import",      # Index 2
            "Control Embedding",   # Index 3
            "Similarity Score",    # Index 4
            "RAG Mapping",         # Index 5
            "Human Validation"     # Index 6
        ]

        # === Create Buttons ===
        for idx, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, i=idx: self.set_active(i))
            self.layout.addWidget(btn) # Add button
            self.buttons.append(btn)

        # --- REMOVED ---
        # self.layout.addStretch() # This line was removed to avoid pushing the layout upwards
        # --- END REMOVED ---

        # Optional: Set addStretch() at the beginning if buttons should be at the bottom?
        # self.layout.addStretch() # Alternatively here, if desired

        # === Activate Initial Selection ===
        if self.buttons:
            self.set_active(self.current_index)

    def set_active(self, index: int):
        """
        Sets the button at the specified index as active (visually) and
        emits the signal to switch the main view.
        (Rest of the method as before)
        """
        if index < 0 or index >= len(self.buttons):
            return

        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == index)

        if index != self.current_index or not self.buttons[index].isChecked():
            self.current_index = index
            self.view_changed.emit(index)
            if not self.buttons[index].isChecked():
                 self.buttons[index].setChecked(True)