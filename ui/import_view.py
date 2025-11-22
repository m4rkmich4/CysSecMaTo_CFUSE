# ui/import_view.py
"""
Defines the user interface for importing OSCAL catalogs.

This view allows the user to select an OSCAL catalog file (JSON)
and initiate the import process into the Neo4j database.
The import process runs in a background thread to avoid blocking the GUI.
Status messages, progress, and errors are displayed in the UI.
"""

import traceback
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
# Import Optional and Callable for type hints (needed in import_manager)
from typing import Optional, Callable # Added for clarity of callback types

# Import the central import logic
try:
    from db.import_manager import import_if_changed
except ImportError:
    print("WARNING: Could not import db.import_manager.")
    # Custom dummy function accepts optional callback
    def import_if_changed(path: Path, progress_callback: Optional[Callable[[str], None]] = None) -> str:
        if progress_callback:
            progress_callback("Dummy function: Import is being simulated.")
        return "ERROR: Import function not available (Import failed)."

# --- Worker Thread for Import ---
class ImportWorker(QObject):
    """
    Executes the OSCAL catalog import in a background thread.

    Takes the file path and calls the `import_if_changed` function
    from `db.import_manager`. Signals the result, progress,
    or errors.

    :ivar progress_update: Signal(str) - Emitted for each progress message
                           during the import.
    :ivar finished: Signal(str) - Emitted when the import attempt is completed.
                    The string contains the final status or error message.
    :ivar error: Signal(str) - Emitted for unexpected errors in the worker itself.
    """
    progress_update = Signal(str) # <-- NEW signal for progress
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, file_path: Path):
        """
        Initializes the worker.

        :param file_path: The path to the catalog file to be imported.
        """
        super().__init__()
        self.file_path = file_path

    def run(self):
        """Executes the import logic and emits the corresponding signals."""
        try:
            if not self.file_path or not self.file_path.exists():
                 self.finished.emit(f"ERROR: File not selected or no longer found: {self.file_path}")
                 return

            # --- Create callback function that emits the signal ---
            report_progress = lambda message: self.progress_update.emit(message)

            # --- Call the central import function and pass the callback ---
            status_message = import_if_changed(
                self.file_path,
                progress_callback=report_progress # <-- Pass callback
            )
            # --- Emit the final result ---
            self.finished.emit(status_message)

        except Exception as e:
            # Catch unexpected errors directly in the worker
            print(f"ERROR in ImportWorker.run:\n{traceback.format_exc()}")
            self.error.emit(f"Unexpected error in import thread: {str(e)}")

# --- The Actual Import View ---
class ImportView(QWidget):
    """
    The widget for the catalog import user interface.

    Contains controls for selecting an OSCAL file, starting the
    import, and displaying status messages and progress.
    """
    def __init__(self):
        """Initializes the ImportView, creates UI, and connects signals."""
        super().__init__()
        self.setObjectName("ImportView")
        self.selected_file_path: Optional[Path] = None
        self.import_thread: Optional[QThread] = None
        self.import_worker: Optional[ImportWorker] = None

        # --- Main Layout ---
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- Area for File Selection ---
        file_selection_layout = QHBoxLayout()
        self.select_button = QPushButton("Select OSCAL Catalog File (.json)...")
        self.select_button.setCursor(Qt.PointingHandCursor)
        self.file_label = QLabel("No file selected.")
        self.file_label.setWordWrap(True)
        file_selection_layout.addWidget(self.select_button)
        file_selection_layout.addWidget(self.file_label, 1)

        # --- Start Import Button ---
        self.import_button = QPushButton("Import Selected File")
        self.import_button.setCursor(Qt.PointingHandCursor)
        self.import_button.setObjectName("importButton")
        self.import_button.setEnabled(False)

        # --- Status Display ---
        self.status_label = QLabel("Status / Progress:") # Label adjusted
        self.status_output = QTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setObjectName("statusOutput")
        # Fixed height often makes less sense for a live log
        # self.status_output.setFixedHeight(150)

        # --- Add Elements to Layout ---
        layout.addLayout(file_selection_layout)
        layout.addWidget(self.import_button) # Without centering
        layout.addWidget(self.status_label)
        layout.addWidget(self.status_output, 1) # Status field expandable

        # --- Connect Signals ---
        self.select_button.clicked.connect(self.select_file)
        self.import_button.clicked.connect(self.start_import_thread)

    def select_file(self):
        """Opens the file dialog and updates the UI."""
        start_dir_path = Path("./files").resolve()
        if not start_dir_path.is_dir(): start_dir_path = Path(".").resolve()
        start_dir = str(start_dir_path)

        file_path_str, _ = QFileDialog.getOpenFileName(
            self, "Select OSCAL Catalog File", start_dir, "JSON Files (*.json)"
        )

        if file_path_str:
            self.selected_file_path = Path(file_path_str)
            self.file_label.setText(f"Selected: {self.selected_file_path.name}")
            self.import_button.setEnabled(True)
            self.status_output.clear() # Clear status on new selection
        else:
            self.selected_file_path = None
            self.file_label.setText("No file selected.")
            self.import_button.setEnabled(False)
            self.status_output.clear()

    def start_import_thread(self):
        """Starts the import process in a background thread."""
        if not self.selected_file_path:
            QMessageBox.warning(self, "No File", "Please select a file first.")
            return
        if self.import_thread and self.import_thread.isRunning():
            QMessageBox.information(self, "Import Running", "The import process is already running.")
            return

        self.set_buttons_enabled(False)
        # Clear status window and add start message
        self.status_output.clear()
        self.status_output.append(f"----\nStarting import for: {self.selected_file_path.name}...")

        # Create thread and worker
        self.import_thread = QThread(self)
        self.import_worker = ImportWorker(self.selected_file_path)
        self.import_worker.moveToThread(self.import_thread)

        # --- Connect Signals ---
        self.import_thread.started.connect(self.import_worker.run)
        # --- NEW: Connect progress signal ---
        self.import_worker.progress_update.connect(self.append_status_message)
        # --- Existing connections ---
        self.import_worker.finished.connect(self.on_import_finished)
        self.import_worker.error.connect(self.on_import_error)
        # --- Cleanup ---
        self.import_worker.finished.connect(self.import_thread.quit)
        self.import_worker.finished.connect(self.import_worker.deleteLater)
        self.import_thread.finished.connect(self.import_thread.deleteLater)
        self.import_thread.finished.connect(self._clear_import_refs)

        # Start thread
        self.import_thread.start()

    # --- NEW Slot for progress messages ---
    def append_status_message(self, message: str):
        """Appends a message to the status text field."""
        self.status_output.append(message) # Appends text and scrolls automatically

    def on_import_finished(self, status_message: str):
        """Slot that processes the final result of the import worker."""
        self.status_output.append(f"----\nFinal result: {status_message}\n----")
        # Show a success/info message only on success / "Already exists"
        # Assuming backend messages containing "FEHLER", "VALIDIERUNGSFEHLER", "existiert bereits"
        # would also be translated if the backend supports it.
        # If these keywords are fixed German strings from backend, conditions should not change.
        # For this translation task, I'm translating them in the condition.
        if "ERROR" not in status_message.upper() and "VALIDATION ERROR" not in status_message.upper():
             QMessageBox.information(self, "Import Completed", status_message)
        elif "already exists" not in status_message.lower(): # No critical box for "already exists"
             QMessageBox.warning(self, "Import Problem", status_message)

        self.set_buttons_enabled(True) # Re-enable buttons

    def on_import_error(self, error_message: str):
        """Slot that handles unexpected errors from the worker thread."""
        self.status_output.append(f"FATAL ERROR in thread: {error_message}\n----")
        QMessageBox.critical(self, "Critical Error",
                             f"An unexpected error occurred in the import thread:\n{error_message}")
        self.set_buttons_enabled(True)

    def _clear_import_refs(self):
        """Resets the thread and worker references after completion."""
        self.import_thread = None
        self.import_worker = None

    def set_buttons_enabled(self, enabled: bool):
        """Enables or disables the action buttons of this view."""
        self.select_button.setEnabled(enabled)
        self.import_button.setEnabled(enabled and (self.selected_file_path is not None))