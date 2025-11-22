# Filename: main_window.py
# UPDATED VERSION: Combined 1-N and M-N Mapping via ControlMappingView

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QStackedWidget, QHBoxLayout, QLabel
)
from PySide6.QtCore import Qt

# --- Custom UI Components ---
from ui.standard_comparison import CybersecurityComparer
from ui.sidebar import Sidebar
from ui.context_retrieval import ContextRetrievalView
from ui.import_view import ImportView
from ui.control_embedding_view import ControlEmbeddingView
from ui.control_mapping_view import ControlMappingView      # UPDATED: Combined Mapping View
from ui.rag_mapping_view import RAGMappingView             # Existing RAG View
from ui.human_validation_view import HumanValidationView

# --- Assets ---
from assets.styles import STYLE_SHEET


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(" 'C-FUSE' --> Cybersecurity Framework Unification & Standard Evaluation")
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(STYLE_SHEET)

        # === Create Views ===
        self.views = QStackedWidget()

        self.comparison_view = CybersecurityComparer()        # Index 0 : Standard Comparison
        self.context_retrieval_view = ContextRetrievalView()  # Index 1 : Context Retrieval
        self.import_view = ImportView()                       # Index 2 : Catalog Import
        self.control_embedding_view = ControlEmbeddingView()  # Index 3 : Control Embedding
        self.control_mapping_view = ControlMappingView()      # Index 4 : Combined 1-N & M-N Mapping
        self.rag_mapping_view = RAGMappingView()              # Index 5 : RAG Mapping
        self.human_validation_view = HumanValidationView()    # Index 6 : Human Validation View

        # === Add Views to Stack (ORDER MUST MATCH SIDEBAR!) ===
        self.views.addWidget(self.comparison_view)        # Index 0
        self.views.addWidget(self.context_retrieval_view) # Index 1
        self.views.addWidget(self.import_view)            # Index 2
        self.views.addWidget(self.control_embedding_view) # Index 3
        self.views.addWidget(self.control_mapping_view)   # Index 4
        self.views.addWidget(self.rag_mapping_view)       # Index 5
        self.views.addWidget(self.human_validation_view)  # Index 6

        # === Sidebar ===
        self.sidebar = Sidebar()
        self.sidebar.setFixedWidth(200)
        self.sidebar.view_changed.connect(self.views.setCurrentIndex)

        # === Layout and Container ===
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.views, 1)

        central_container = QWidget()
        central_container.setLayout(main_layout)
        self.setCentralWidget(central_container)
