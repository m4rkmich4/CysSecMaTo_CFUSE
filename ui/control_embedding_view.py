# Filename: ui/control_embedding_view.py

"""
Qt-based view for inspecting and generating embeddings for control descriptions.

This module provides a dedicated GUI widget that allows users to:

* Select a catalog (and optionally filter by group / special filter mode),
* Inspect which controls already have description embeddings in Neo4j, and
* Trigger batch generation of embeddings for selected controls in a
  background thread.

The heavy lifting (model initialization, token handling, embedding creation,
and database writes) is delegated to functions in :mod:`logic.control_embedding`
and :mod:`db.queries_embeddings`. This view focuses on orchestration and
user interaction.
"""

import logging
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QMessageBox,
    QCheckBox,  # QSplitter, QFrame removed, as not directly used
)
from PySide6.QtCore import Qt, QThread, Signal, QObject

# Database functions for Catalog/Group selection
from db.queries_embeddings import get_all_catalogs, get_groups_for_catalog
# Logic functions
from logic.control_embedding import (
    get_control_embedding_status,
    create_embeddings_for_parts,
    initialize_embedding_system,
    get_current_active_model_name,
)

log = logging.getLogger(__name__)


class EmbeddingWorker(QObject):
    """Background worker object that generates embeddings in a worker thread.

    This QObject is moved to a :class:`QThread` and executes the potentially
    long-running embedding creation via :func:`create_embeddings_for_parts`.
    Progress and final status are communicated back to the GUI using signals.

    Attributes:
        finished (Signal): Emitted when the worker has completed processing.
            Carries a human-readable summary message.
        progress (Signal): Emitted for intermediate status messages during
            embedding creation (e.g. "Processing part 10/50 ...").
    """

    finished = Signal(str)
    progress = Signal(str)

    def __init__(self, entries: List[Dict[str, Any]]):
        """Initialize the worker with a list of part entries.

        Args:
            entries: List of dictionaries describing the parts that should
                receive embeddings. The concrete schema is defined by the
                retrieval in :func:`get_control_embedding_status`.
        """
        super().__init__()
        self.entries = entries

    def run(self) -> None:
        """Run the embedding creation for the configured entries.

        The method delegates to :func:`create_embeddings_for_parts` and
        forwards its progress messages to the GUI via the ``progress`` signal.
        Any errors are logged and also reported via the ``finished`` signal
        as an error message.
        """
        try:
            created = create_embeddings_for_parts(
                self.entries, progress_callback=self.progress.emit
            )
            self.finished.emit(f"Embedding generation completed. ({created} created)")
        except Exception as e:
            logging.error(f"Error in EmbeddingWorker: {e}", exc_info=True)
            self.finished.emit(f"ERROR in Worker: {type(e).__name__} - {str(e)}")


class ControlEmbeddingView(QWidget):
    """Qt view for managing and generating control embeddings.

    This widget provides a compact interface for:

    * Selecting a catalog and filtering controls (all, only without group,
      group-specific),
    * Inspecting whether a description embedding is already present and which
      model was used, and
    * Marking specific controls for embedding generation and running this
      process in a background thread.

    The view is intended as an operational tool for monitoring and evolving
    the embedding coverage of a Neo4j-based catalog.
    """

    def __init__(self) -> None:
        """Initialize the control embedding view and set up the UI."""
        super().__init__()
        self.setMinimumWidth(950)

        # In-memory state for currently available catalogs and table entries
        self.catalogs: List[Dict[str, Any]] = get_all_catalogs()
        self.current_entries: List[Dict[str, Any]] = []

        # Thread-related references (reset via _clear_thread_references)
        self.embedding_thread: Optional[QThread] = None
        self.embedding_worker: Optional[EmbeddingWorker] = None

        # --- UI Elements ---
        self.catalog_selector = QComboBox()
        self.group_selector = QComboBox()
        self.load_button = QPushButton("Load")
        self.reload_button = QPushButton("🔁")
        self.generate_button = QPushButton("Generate Selected Embeddings")
        self.status_output = QTextEdit()
        self.status_output.setReadOnly(True)
        self.active_model_label = QLabel("Active Model: -")

        # Table to display controls and their embedding status
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["✔", "Control-ID", "Title", "Has Embedding", "Method"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft
        )

        # --- Layout ---
        layout = QVBoxLayout(self)
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Catalog:", self))
        top_row.addWidget(self.catalog_selector, 1)
        top_row.addSpacing(20)
        top_row.addWidget(QLabel("Group:", self))
        top_row.addWidget(self.group_selector, 1)
        top_row.addWidget(self.load_button)
        top_row.addWidget(self.reload_button)
        top_row.addStretch()
        top_row.addWidget(self.active_model_label)
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        layout.addWidget(self.generate_button)
        layout.addWidget(QLabel("Status:", self))
        layout.addWidget(self.status_output)

        # --- Signals ---
        self.catalog_selector.currentIndexChanged.connect(self.update_group_selector)
        self.load_button.clicked.connect(self.load_controls)
        self.reload_button.clicked.connect(self.reload_catalog_data)
        self.generate_button.clicked.connect(self.run_embedding_generation)

        # --- Initialization ---
        self.populate_catalogs()
        self.update_active_model_label()

    # --- Helper / UI update methods -------------------------------------

    def update_active_model_label(self) -> None:
        """Update the label that displays the currently active embedding model.

        The label is driven by :func:`get_current_active_model_name`. If no
        model has been successfully initialized yet, "Not initialized" is
        shown.
        """
        active_model = get_current_active_model_name()
        display_name = active_model if active_model else "Not initialized"
        self.active_model_label.setText(f"Active Model: {display_name}")

    def populate_catalogs(self) -> None:
        """Populate the catalog selector with all available catalogs.

        The current selection (if any) is preserved where possible. After
        updating the catalog selector, the group selector is refreshed via
        :meth:`update_group_selector`.

        Errors are logged and reported via a message box.
        """
        current_uuid = self.catalog_selector.currentData()
        self.catalog_selector.clear()
        selected_index = 0
        try:  # Error handling for get_all_catalogs
            self.catalogs = get_all_catalogs()
            for i, cat in enumerate(self.catalogs):
                self.catalog_selector.addItem(cat["title"], cat["uuid"])
                if cat["uuid"] == current_uuid:
                    selected_index = i
            if self.catalogs:
                if selected_index < self.catalog_selector.count():
                    self.catalog_selector.setCurrentIndex(selected_index)
                elif self.catalog_selector.count() > 0:
                    self.catalog_selector.setCurrentIndex(0)
            # Always update groups for the new catalog selection.
            self.update_group_selector()
        except Exception as e:
            log.error(f"Error loading catalogs: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Catalog list could not be loaded:\n{e}",
            )

    def update_group_selector(self) -> None:
        """Update the group selector based on the currently selected catalog.

        The group selector supports several special filter entries:

        * ``<All (complete)>`` (``"__ALL__"``): Show all controls of the
          catalog, ignoring group membership.
        * ``<Only Controls without Group>`` (``"__NOGROUP__"``): Show only
          controls that are not associated with any group.
        * ``<All (Default)>`` (``None`` as data): Use the default filter
          logic that balances group-aware and non-group controls.

        Any additional entries correspond to concrete groups returned by
        :func:`get_groups_for_catalog`.
        """
        current_group_data = self.group_selector.currentData()
        self.group_selector.clear()
        uuid = self.catalog_selector.currentData()
        if not uuid:
            self.group_selector.addItem("<Select Catalog>", None)
            return
        try:
            groups = get_groups_for_catalog(uuid)
            self.group_selector.addItem("<All (complete)>", "__ALL__")
            self.group_selector.addItem("<Only Controls without Group>", "__NOGROUP__")
            self.group_selector.addItem("<All (Default)>", None)
            selected_index = 2  # Default to "<All (Default)>"
            for i, g in enumerate(groups):
                self.group_selector.addItem(g["title"], g["id"])
                if g["id"] == current_group_data:
                    selected_index = i + 3
            if selected_index < self.group_selector.count():
                self.group_selector.setCurrentIndex(selected_index)
            else:
                self.group_selector.setCurrentIndex(2)  # Default to "<All (Default)>"
        except Exception as e:
            self.append_status(f"❌ Error loading groups: {e}")
            log.error(f"Error loading groups for catalog {uuid}:", exc_info=True)
            self.group_selector.addItem("<Error>", None)

    def load_controls(self) -> None:
        """Load control embedding status for the selected catalog/group.

        This method:

        * Resolves the current catalog UUID and group filter mode,
        * Requests data via :func:`get_control_embedding_status`, and
        * Populates the table with one row per control description part.

        Each row contains a checkbox in the first column that determines
        whether an embedding should be generated for this control when the
        user starts the embedding process.
        """
        self.table.setRowCount(0)
        uuid = self.catalog_selector.currentData()
        group_id_data = self.group_selector.currentData()
        if not uuid:
            QMessageBox.warning(
                self, "No Catalog", "Please select a catalog first."
            )
            return

        # Interpret special group selector values as filter flags.
        only_without_group = group_id_data == "__NOGROUP__"
        show_all_controls = group_id_data == "__ALL__"
        query_group_id = None
        if not show_all_controls and not only_without_group and group_id_data is not None:
            query_group_id = group_id_data

        self.append_status(
            f"Loading Controls for catalog '{self.catalog_selector.currentText()}' "
            f"(Filter: {self.group_selector.currentText()})..."
        )
        try:
            data = get_control_embedding_status(
                catalog_uuid=uuid,
                group_id=query_group_id,
                only_without_group=only_without_group,
                show_all_controls=show_all_controls,
            )
        except Exception as e:
            self.append_status(f"❌ Error loading Controls: {e}")
            logging.error("Error in load_controls:", exc_info=True)
            QMessageBox.critical(
                self,
                "Database Error",
                f"Error loading Control data:\n{e}",
            )
            return

        if not data:
            self.append_status("ℹ️ No matching Controls found.")
        else:
            self.append_status(f"{len(data)} Controls loaded.")

        self.current_entries = data
        self.table.setRowCount(len(data))

        # Fill the table: checkbox + metadata per control
        for i, entry in enumerate(data):
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            chk = QCheckBox()
            # Pre-select rows that do NOT yet have an embedding.
            chk.setChecked(not entry.get("has_embedding", False))
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_widget.setLayout(chk_layout)
            self.table.setCellWidget(i, 0, chk_widget)

            self.table.setItem(
                i, 1, QTableWidgetItem(entry.get("control_id", ""))
            )
            self.table.setItem(
                i, 2, QTableWidgetItem(entry.get("control_title", ""))
            )

            has_emb = entry.get("has_embedding", False)
            emb_item = QTableWidgetItem("✅ Yes" if has_emb else "❌ No")
            self.table.setItem(i, 3, emb_item)
            self.table.setItem(
                i,
                4,
                QTableWidgetItem(entry.get("embedding_method") or "-"),
            )

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )

    # --- Embedding generation / threading --------------------------------

    def run_embedding_generation(self) -> None:
        """Start embedding generation for all marked rows in a background thread.

        This method collects all controls whose checkbox is checked, ensures
        that an embedding model is initialized via
        :func:`initialize_embedding_system`, and then launches an
        :class:`EmbeddingWorker` in a :class:`QThread`.

        Buttons are disabled during processing and re-enabled once the worker
        has finished.
        """
        entries_to_process: List[Dict[str, Any]] = []
        for i in range(self.table.rowCount()):
            widget = self.table.cellWidget(i, 0)
            if widget:
                # Safely locate the checkbox within the cell widget.
                chk = widget.findChild(QCheckBox)
                if chk and chk.isChecked():
                    entries_to_process.append(self.current_entries[i])

        if not entries_to_process:
            QMessageBox.information(
                self,
                "No Selection",
                "Please mark at least one row (✔) for which embeddings "
                "should be generated.",
            )
            return

        # No check for self.embedding_thread.isRunning() here anymore;
        # the button state is used to prevent concurrent runs.
        self.status_output.clear()
        self.append_status(
            f"Starting embedding generation for {len(entries_to_process)} entries..."
        )
        self.generate_button.setEnabled(False)
        self.load_button.setEnabled(False)
        self.reload_button.setEnabled(False)

        # Ensure the embedding system is initialized before starting the worker.
        self.append_status("Initializing embedding system...")
        model_to_ensure = (
            get_current_active_model_name()
            or "sentence-transformers/all-mpnet-base-v2"
        )
        if not initialize_embedding_system(
            model_name=model_to_ensure, progress_callback=self.append_status
        ):
            self.append_status("❌ Error: Embedding system could not be initialized.")
            QMessageBox.critical(
                self,
                "Initialization Error",
                "The embedding model could not be loaded.\n"
                "Please check network or consult log files.",
            )
            self.generate_button.setEnabled(True)
            self.load_button.setEnabled(True)
            self.reload_button.setEnabled(True)
            return

        self.append_status("✅ Embedding system ready.")
        self.update_active_model_label()

        # Create worker and thread
        self.embedding_worker = EmbeddingWorker(entries_to_process)
        self.embedding_thread = QThread(self)
        self.embedding_worker.moveToThread(self.embedding_thread)

        # Connect signals: start, progress, finish, cleanup
        self.embedding_thread.started.connect(self.embedding_worker.run)
        self.embedding_worker.progress.connect(self.append_status)
        self.embedding_worker.finished.connect(self.on_embedding_done)
        # Cleanup connections
        self.embedding_worker.finished.connect(self.embedding_thread.quit)
        self.embedding_worker.finished.connect(self.embedding_worker.deleteLater)
        self.embedding_thread.finished.connect(self.embedding_thread.deleteLater)
        # Reset references when thread finishes
        self.embedding_thread.finished.connect(self._clear_thread_references)

        self.append_status("Starting background worker...")
        self.embedding_thread.start()

    def append_status(self, msg: str) -> None:
        """Append a status message to the status output widget.

        The method also scrolls the text view to the bottom so that the
        most recent messages remain visible.

        Args:
            msg: Text message to be appended to the status output.
        """
        try:
            self.status_output.append(msg)
            self.status_output.verticalScrollBar().setValue(
                self.status_output.verticalScrollBar().maximum()
            )
        except Exception as e:
            log.error(f"Error appending status message: {e}", exc_info=True)

    def on_embedding_done(self, final_msg: str) -> None:
        """Handle completion of the embedding worker.

        This slot is triggered when :class:`EmbeddingWorker` emits
        the ``finished`` signal.

        Args:
            final_msg: Human-readable summary message from the worker
                (e.g. number of embeddings created or an error note).
        """
        self.append_status("---\n" + final_msg)
        # Re-enable buttons after background job has finished.
        self.generate_button.setEnabled(True)
        self.load_button.setEnabled(True)
        self.reload_button.setEnabled(True)

        # Reload table to show updated embedding status.
        try:
            self.load_controls()
        except Exception as e:
            log.error(
                f"Error reloading controls in on_embedding_done: {e}",
                exc_info=True,
            )
            self.append_status(f"❌ Error updating the table: {e}")

    def _clear_thread_references(self) -> None:
        """Reset worker and thread references after the thread has finished.

        This is a small housekeeping helper to avoid keeping stale references
        once the embedding thread has been stopped and deleted.
        """
        log.debug("Thread finished, deleting references to worker and thread.")
        self.embedding_thread = None
        self.embedding_worker = None

    # --- Catalog reload / close handling ---------------------------------

    def reload_catalog_data(self) -> None:
        """Reload catalog data and refresh the corresponding selectors.

        This method is typically triggered by the reload button. It refetches
        the catalog list via :func:`get_all_catalogs` and calls
        :meth:`populate_catalogs` to update the UI. Any errors are logged
        and surfaced via a message box and status output.
        """
        self.append_status("Reloading catalog data...")
        try:
            # Re-fetch catalog list and repopulate selectors.
            self.catalogs = get_all_catalogs()
            self.populate_catalogs()
            self.append_status("🔄 Catalog and group list updated.")
        except Exception as e:
            self.append_status(f"❌ Error reloading catalog data: {e}")
            logging.error("Error in reload_catalog_data:", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Error reloading catalog data:\n{e}",
            )

    def closeEvent(self, event) -> None:
        """Handle the widget close event and stop any running worker thread.

        If an embedding thread is still running, the method attempts a
        graceful shutdown via ``quit()`` and ``wait()``. If the thread does
        not stop within a short timeout, a forced ``terminate()`` is used
        as a last resort to avoid leaving background threads behind.

        Args:
            event: The Qt close event instance.
        """
        if self.embedding_thread and self.embedding_thread.isRunning():
            self.append_status("Stopping running embedding process...")
            self.embedding_thread.quit()
            if not self.embedding_thread.wait(1000):  # Wait 1 sec
                logging.warning(
                    "Embedding thread could not be stopped cleanly."
                )
                self.embedding_thread.terminate()  # Force terminate if not quitting
                self.embedding_thread.wait()  # Wait for termination
        super().closeEvent(event)