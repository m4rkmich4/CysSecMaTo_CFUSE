# ui/context_retrieval.py
"""
This module defines the view for context retrieval and comparison.

It allows users to select two standards, generate embeddings for the
underlying data, and perform AI-assisted generation
based on the descriptions of the selected standards.
Both potentially long-running operations (embedding generation and
LLM call) are executed in background threads.
"""

import json
# import os # Replaced by pathlib
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QTextEdit, QMessageBox, QComboBox, QApplication, QTextBrowser
)
from PySide6.QtCore import Qt, QThread, Signal, QObject

# Import custom modules
try:
    # This function is not directly needed here for the embedding process,
    # but the worker might use it internally if the retriever needs it.
    # The main import happens in retrieval.fake_retriever.
    pass # No direct import of import_manager needed here
except ImportError:
    pass # Error handling for the case that db is not in the path

from retrieval.fake_retriever import FakeRetriever
from config.prompts_rag import build_rag_prompt
from logic.llm_interface import call_local_llm

# Use pathlib for paths
DATA_PATH = Path("files") / "RAG.json"

# --- Worker for Embedding Generation ---
class EmbeddingWorker(QObject):
    """
    Executes the embedding calculation in a background thread.

    :ivar finished: Signal(bool, str) - Emitted when finished.
                    Parameters: Success (True/False), Message (str).
    """
    finished = Signal(bool, str)

    def __init__(self, retriever_instance: FakeRetriever):
        """
        Initializes the worker.

        :param retriever_instance: The instance of FakeRetriever,
                                   whose method should be called.
        """
        super().__init__()
        self.retriever = retriever_instance

    def run(self):
        """Starts the recalculation of embeddings in the retriever."""
        try:
            # Execute the potentially long-running operation
            self.retriever.recompute_embeddings()
            self.finished.emit(True, "Embeddings successfully generated/updated.")
        except Exception as e:
            import traceback
            print(f"ERROR in EmbeddingWorker.run:\n{traceback.format_exc()}")
            self.finished.emit(False, f"Error during embedding generation: {str(e)}")

# --- Worker for LLM Call ---
class LlmWorker(QObject):
    """
    Executes the LLM call in a background thread.

    :ivar finished: Signal(bool, str) - Emitted when finished.
                    Parameters: Success (True/False), Result/Error (str).
    """
    finished = Signal(bool, str)

    def __init__(self, prompt: str):
        """
        Initializes the worker.

        :param prompt: The prompt to be sent to the LLM.
        """
        super().__init__()
        self.prompt = prompt

    def run(self):
        """Calls the local LLM and emits the result."""
        try:
            response = call_local_llm(self.prompt)
            self.finished.emit(True, response)
        except Exception as e:
             import traceback
             print(f"ERROR in LlmWorker.run:\n{traceback.format_exc()}")
             self.finished.emit(False, f"Error calling the LLM: {str(e)}")

# --- The Main View Class ---
class ContextRetrievalView(QWidget):
    """
    The user interface for standard comparison and context retrieval.

    Provides selection options for two standards, buttons to generate
    embeddings and to start the LLM-based comparison, as well as a
    text field to display the results. Long-running processes are executed in
    separate threads.
    """
    def __init__(self):
        """Initializes the view, creates UI elements, and connects signals."""
        super().__init__()
        self.setMinimumWidth(900)
        self.retriever = FakeRetriever() # Create retriever instance
        # Initialize references for running threads and workers
        self.embedding_thread = None
        self.embedding_worker = None
        self.llm_thread = None
        self.llm_worker = None

        # --- Create UI Elements ---
        self.standard_a = QComboBox()
        self.standard_b = QComboBox()
        self.embed_button = QPushButton("Generate Embeddings")
        self.retrieve_button = QPushButton("Generate with Retrieval")
        self.result_area = QTextBrowser() # Use QTextBrowser
        self.result_area.setOpenExternalLinks(True)

        # --- Create Layout ---
        layout = QVBoxLayout(self) # Main layout for the view

        # Helper function for labeled widgets (unchanged)
        def labeled_widget(label_text, widget):
            box = QVBoxLayout()
            label = QLabel(label_text)
            box.addWidget(label)
            box.addWidget(widget)
            return box

        # Horizontal layout for ComboBoxes (unchanged)
        hbox1 = QHBoxLayout()
        hbox1.addLayout(labeled_widget("Standard A:", self.standard_a))
        hbox1.addSpacing(20)
        hbox1.addLayout(labeled_widget("Standard B:", self.standard_b))

        # Add elements to the main layout
        layout.addLayout(hbox1)
        # --- Add buttons WITHOUT additional alignment ---
        layout.addWidget(self.embed_button)
        layout.addWidget(self.retrieve_button)
        # --- End of change ---
        layout.addWidget(QLabel("Retrieval Result:"))
        layout.addWidget(self.result_area, 1) # Result area should expand

        self.setLayout(layout)

        # --- Connect Signals ---
        self.embed_button.clicked.connect(self.start_embedding_generation) # New slot for thread
        self.retrieve_button.clicked.connect(self.start_retrieval)         # New slot for thread

        # --- Initialization ---
        self._load_titles() # Populate ComboBoxes

    def _load_titles(self):
        """Loads titles from the JSON file into the ComboBoxes."""
        try:
            if not DATA_PATH.exists():
                QMessageBox.warning(self, "File Not Found", f"Data file {DATA_PATH} not found.")
                return

            with DATA_PATH.open("r", encoding='utf-8') as f:
                data = json.load(f)

            titles = [doc.get("title") for doc in data if doc.get("title")]
            if not titles:
                 QMessageBox.warning(self, "No Data", f"No documents with titles in {DATA_PATH} found.")
                 return

            self.standard_a.clear()
            self.standard_b.clear()
            self.standard_a.addItems(titles)
            self.standard_b.addItems(titles)

            if len(titles) > 1:
                self.standard_b.setCurrentIndex(1) # Sensible default setting

        except json.JSONDecodeError as e:
             QMessageBox.critical(self, "JSON Error", f"Error reading {DATA_PATH}:\nInvalid JSON: {str(e)}")
        except Exception as e:
            import traceback
            print(f"ERROR in _load_titles:\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Error", f"Error loading document titles:\n{str(e)}")

    # --- Embedding Generation with Threading ---
    def start_embedding_generation(self):
        """Starts the embedding generation in a background thread."""
        if self.embedding_thread and self.embedding_thread.isRunning():
            QMessageBox.information(self, "Already Running", "Embedding generation is already running.")
            return

        self.set_buttons_enabled(False) # Disable buttons
        # Optional: Provide brief feedback
        QMessageBox.information(self, "Started", "Starting embedding generation...")

        self.embedding_thread = QThread(self) # Set parent for better management
        self.embedding_worker = EmbeddingWorker(self.retriever)
        self.embedding_worker.moveToThread(self.embedding_thread)

        # Connections for execution and cleanup
        self.embedding_thread.started.connect(self.embedding_worker.run)
        self.embedding_worker.finished.connect(self.on_embedding_finished)
        self.embedding_worker.finished.connect(self.embedding_thread.quit)
        self.embedding_worker.finished.connect(self.embedding_worker.deleteLater)
        self.embedding_thread.finished.connect(self.embedding_thread.deleteLater)
        self.embedding_thread.finished.connect(self._clear_embedding_refs)

        self.embedding_thread.start()

    def on_embedding_finished(self, success: bool, message: str):
        """Slot that reacts to the 'finished' signal of the EmbeddingWorker."""
        if success:
            QMessageBox.information(self, "Embedding Generation", message)
        else:
            QMessageBox.critical(self, "Embedding Error", message)
        self.set_buttons_enabled(True) # Re-enable buttons

    def _clear_embedding_refs(self):
        """Resets the references for the embedding thread/worker."""
        self.embedding_thread = None
        self.embedding_worker = None

    # --- Retrieval with Threading ---
    def start_retrieval(self):
        """Prepares the RAG process and starts it in a background thread."""
        if self.llm_thread and self.llm_thread.isRunning():
             QMessageBox.information(self, "Already Running", "Retrieval is already running.")
             return

        # --- Data preparation (in GUI thread) ---
        try:
            title_a = self.standard_a.currentText()
            title_b = self.standard_b.currentText()
            doc_a = self.retriever.get_document_by_title(title_a)
            doc_b = self.retriever.get_document_by_title(title_b)

            if not doc_a or not doc_b: raise ValueError("Selected standards not found.")
            desc_a = doc_a.get("description"); desc_b = doc_b.get("description")
            if not desc_a or not desc_b: raise ValueError("No description for one/both document(s).")

            query = f"Compare standard '{title_a}' with '{title_b}'."
            context_snippets = [desc_a, desc_b]
            prompt = build_rag_prompt(query=query, contexts=context_snippets)

        except Exception as e:
            QMessageBox.critical(self, "Preparation Error", f"Error before LLM call:\n{str(e)}")
            return # Abort if preparation fails

        # --- Prepare UI and start thread ---
        self.set_buttons_enabled(False)
        self.result_area.setPlainText("Generating response from LLM (may take a while)...")
        QApplication.setOverrideCursor(Qt.WaitCursor)

        self.llm_thread = QThread(self) # Set parent
        self.llm_worker = LlmWorker(prompt)
        self.llm_worker.moveToThread(self.llm_thread)

        # Connections for execution and cleanup
        self.llm_thread.started.connect(self.llm_worker.run)
        self.llm_worker.finished.connect(self.on_retrieval_finished)
        self.llm_worker.finished.connect(self.llm_thread.quit)
        self.llm_worker.finished.connect(self.llm_worker.deleteLater)
        self.llm_thread.finished.connect(self.llm_thread.deleteLater)
        self.llm_thread.finished.connect(self._clear_llm_refs)

        self.llm_thread.start()

    def on_retrieval_finished(self, success: bool, result_or_error: str):
        """Slot that reacts to the 'finished' signal of the LlmWorker."""
        QApplication.restoreOverrideCursor() # ALWAYS reset cursor
        if success:
            self.result_area.setPlainText(result_or_error)
        else:
            # Show error in text field AND as popup
            self.result_area.setPlainText(f"Error during retrieval:\n{result_or_error}")
            QMessageBox.critical(self, "Retrieval Error", f"Retrieval failed:\n{result_or_error}")
        self.set_buttons_enabled(True) # Re-enable buttons

    def _clear_llm_refs(self):
         """Resets the references for the LLM thread/worker."""
         self.llm_thread = None
         self.llm_worker = None

    def set_buttons_enabled(self, enabled: bool):
        """Enables or disables the main action buttons."""
        self.embed_button.setEnabled(enabled)
        self.retrieve_button.setEnabled(enabled)
        # Optional: Also disable ComboBoxes during processing
        # self.standard_a.setEnabled(enabled)
        # self.standard_b.setEnabled(enabled)