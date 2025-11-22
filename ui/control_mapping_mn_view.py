# Filename: ui/control_mapping_mn_view.py
# Separated M-N Mapping View (purely for many-to-many comparison)

"""
Qt-based view for many-to-many control mapping using similarity embeddings.

This module provides a dedicated GUI widget that allows users to:

* Select a **source** and **target** catalog (each optionally filtered by group),
* Trigger a many-to-many similarity process between all eligible controls
  (backed by precomputed embeddings), and
* Inspect and persist the resulting similarity relationships to Neo4j.

All heavy computation and persistence are delegated to functions in
:mod:`logic.control_mapping`. This view primarily orchestrates the process,
handles background execution, and provides user feedback.
"""

import logging
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QMessageBox,
    QSplitter,
)
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject

from db.queries_embeddings import get_all_catalogs, get_groups_for_catalog
from logic.control_mapping import (
    execute_many_to_many_similarity_process,
    store_similarity_relations,
)
from logic.control_embedding import get_current_active_model_name

log = logging.getLogger(__name__)


# --- Background Task -----------------------------------------------------


class BulkSimilaritySignals(QObject):
    """Signals emitted by :class:`BulkSimilarityTask` during M-N processing.

    Attributes:
        finished (Signal): Emitted when the many-to-many process completes.
            Carries a dictionary with detailed statistics and top results.
        error (Signal): Emitted if an exception occurs during processing.
            Carries a human-readable error message.
        progress (Signal): Emitted for intermediate status messages
            (e.g. "Starting M-N calculation …").
    """

    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(str)


class BulkSimilarityTask(QRunnable):
    """QRunnable executing the many-to-many similarity process in the background.

    This task is submitted to a :class:`QThreadPool` and encapsulates all
    parameters required to call
    :func:`execute_many_to_many_similarity_process`. Results and errors are
    reported back to the GUI using the associated :class:`BulkSimilaritySignals`.
    """

    def __init__(
        self,
        source_cat_uuid: str,
        source_grp_id: Optional[str],
        target_cat_uuid: str,
        target_grp_id: Optional[str],
        embedding_model_name: str,
        similarity_threshold: float,
        top_n_display: float,
    ):
        """Initialize the bulk similarity task.

        Args:
            source_cat_uuid: UUID of the source catalog to be compared.
            source_grp_id: Optional group id to restrict the source side.
                If ``None``, all eligible controls of the source catalog
                are considered.
            target_cat_uuid: UUID of the target catalog to be compared.
            target_grp_id: Optional group id to restrict the target side.
                If ``None``, all eligible controls of the target catalog
                are considered.
            embedding_model_name: Name of the embedding model that produced
                the vectors used in the similarity calculation. Used
                primarily for logging and traceability.
            similarity_threshold: Minimum similarity score for a relation
                to be considered relevant and eventually persisted.
            top_n_display: Upper bound for the number of top results that
                should be included in the returned summary for UI display.
        """
        super().__init__()
        self.signals = BulkSimilaritySignals()
        self.source_cat_uuid = source_cat_uuid
        self.source_grp_id = source_grp_id
        self.target_cat_uuid = target_cat_uuid
        self.target_grp_id = target_grp_id
        self.embedding_model_name = embedding_model_name
        self.similarity_threshold = similarity_threshold
        self.top_n_display = top_n_display

    def run(self) -> None:
        """Execute the many-to-many similarity process and emit signals.

        The method delegates to
        :func:`execute_many_to_many_similarity_process` with the configured
        parameters. On success, the full result dictionary is emitted via
        ``finished`` and a human-readable completion message is sent via
        ``progress``. In case of errors, a short error message is emitted
        via ``error`` and details are logged.
        """
        self.signals.progress.emit("Starting M-N calculation & storage…")
        try:
            result = execute_many_to_many_similarity_process(
                source_catalog_uuid=self.source_cat_uuid,
                source_group_id=self.source_grp_id,
                target_catalog_uuid=self.target_cat_uuid,
                target_group_id=self.target_grp_id,
                embedding_model_name=self.embedding_model_name,
                similarity_threshold=self.similarity_threshold,
                top_n_for_display=self.top_n_display,
            )
            self.signals.finished.emit(result)
            count = result.get("statistics", {}).get("relationships_written", 0)
            self.signals.progress.emit(f"M-N finished. {count} relationships saved.")
        except Exception as e:
            log.error("Error in BulkSimilarityTask:", exc_info=True)
            self.signals.error.emit(str(e))


# --- Main View -----------------------------------------------------------


class ControlMappingMNView(QWidget):
    """Qt view for many-to-many similarity-based control mappings.

    This view is intended for bulk mapping scenarios, where an entire
    catalog (or group within a catalog) is compared to another catalog/group.
    The workflow is:

    1. Select **source** catalog and optional group.
    2. Select **target** catalog and optional group.
    3. Start the M-N similarity process, which runs in a background thread.
    4. Inspect top results in a table.
    5. Persist selected similarity relations to Neo4j.

    Embedding vectors are assumed to be precomputed; the view does not
    perform embedding generation itself.
    """

    def __init__(self) -> None:
        """Initialize the many-to-many control mapping view and its UI."""
        super().__init__()
        self.setObjectName("ControlMappingMNView")
        self.setMinimumWidth(1000)
        self.threadpool = QThreadPool.globalInstance()

        # Cached catalog list and current result set
        self.catalogs: List[Dict[str, Any]] = []
        self.results_data: List[Dict[str, Any]] = []

        # --- UI Elements ---
        self.source_catalog_selector = QComboBox()
        self.source_group_selector = QComboBox()
        self.target_catalog_selector = QComboBox()
        self.target_group_selector = QComboBox()
        self.reload_button = QPushButton("🔁")
        self.reload_button.setToolTip("Reload catalog/group list")

        self.start_mapping_button = QPushButton("Start")
        self.start_mapping_button.setEnabled(False)

        self.save_button = QPushButton("Save")
        self.save_button.setEnabled(False)

        self.results_table = QTableWidget(0, 6)
        self.results_table.setHorizontalHeaderLabels(
            ["Source", "Source-ID", "Target-ID", "Target Title", "Score", "Category"]
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.status_output = QTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setMaximumHeight(150)

        # --- Layout ---
        main_lay = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        # Left panel: Source configuration
        left = QWidget()
        ll = QVBoxLayout(left)

        # Header with title and reload button
        header1 = QHBoxLayout()
        header1.addWidget(QLabel("1. Source"))
        header1.addStretch()
        header1.addWidget(self.reload_button)
        ll.addLayout(header1)

        # Selection row for source catalog/group
        row = QHBoxLayout()
        row.addWidget(QLabel("Catalog:"))
        row.addWidget(self.source_catalog_selector, 1)
        row.addWidget(QLabel("Group:"))
        row.addWidget(self.source_group_selector, 1)
        ll.addLayout(row)
        splitter.addWidget(left)

        # Right panel: Target configuration
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("2. Target"))
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Catalog:"))
        row2.addWidget(self.target_catalog_selector, 1)
        row2.addWidget(QLabel("Group:"))
        row2.addWidget(self.target_group_selector, 1)
        rl.addLayout(row2)
        splitter.addWidget(right)

        main_lay.addWidget(splitter)

        # Control buttons for starting mapping and saving results
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self.start_mapping_button)
        btns.addWidget(self.save_button)
        btns.addStretch()
        main_lay.addLayout(btns)

        main_lay.addWidget(QLabel("Results"))
        main_lay.addWidget(self.results_table, 1)
        main_lay.addWidget(QLabel("Status"))
        main_lay.addWidget(self.status_output)

        # --- Signals ---
        self.reload_button.clicked.connect(self.reload_catalog_data)
        self.source_catalog_selector.currentIndexChanged.connect(
            self.update_source_group_selector
        )
        self.target_catalog_selector.currentIndexChanged.connect(
            self.update_target_group_selector
        )
        self.source_group_selector.currentIndexChanged.connect(
            self.update_start_button_state
        )
        self.target_group_selector.currentIndexChanged.connect(
            self.update_start_button_state
        )
        self.start_mapping_button.clicked.connect(self.start_mapping_process)
        self.save_button.clicked.connect(self._save_relations)

        # Initial population of catalog selectors
        self.populate_catalog_selectors()

    # --- Catalog / group selector helpers --------------------------------

    def populate_catalog_selectors(self) -> None:
        """Populate source and target catalog selectors with all catalogs.

        The current selections (if any) are preserved where possible. After
        updating the catalogs, the corresponding group selectors are refreshed
        via :meth:`update_source_group_selector` and
        :meth:`update_target_group_selector`.
        """
        try:
            self.catalogs = get_all_catalogs()
            s_cur = self.source_catalog_selector.currentData()
            t_cur = self.target_catalog_selector.currentData()

            # Temporarily block signals to avoid cascading updates.
            self.source_catalog_selector.blockSignals(True)
            self.target_catalog_selector.blockSignals(True)

            self.source_catalog_selector.clear()
            self.target_catalog_selector.clear()
            self.source_catalog_selector.addItem("<Select Catalog>", None)
            self.target_catalog_selector.addItem("<Select Catalog>", None)

            for cat in self.catalogs:
                self.source_catalog_selector.addItem(cat["title"], cat["uuid"])
                self.target_catalog_selector.addItem(cat["title"], cat["uuid"])

            # Restore previous selections if still present.
            if s_cur:
                idx = self.source_catalog_selector.findData(s_cur)
                if idx >= 0:
                    self.source_catalog_selector.setCurrentIndex(idx)
            if t_cur:
                idx = self.target_catalog_selector.findData(t_cur)
                if idx >= 0:
                    self.target_catalog_selector.setCurrentIndex(idx)

        finally:
            self.source_catalog_selector.blockSignals(False)
            self.target_catalog_selector.blockSignals(False)
            self.update_source_group_selector()
            self.update_target_group_selector()

    def update_source_group_selector(self) -> None:
        """Update the source group selector based on the selected source catalog.

        If no catalog is selected, a single ``<All Groups>`` entry is shown
        with ``None`` as data. Otherwise, the selector contains:

        * ``<All Groups>`` (``None``) to include all groups, plus
        * one entry per group returned by :func:`get_groups_for_catalog`.
        """
        self.source_group_selector.clear()
        cat = self.source_catalog_selector.currentData()
        if not cat:
            self.source_group_selector.addItem("<All Groups>", None)
        else:
            self.source_group_selector.addItem("<All Groups>", None)
            for g in get_groups_for_catalog(cat):
                self.source_group_selector.addItem(g["title"], g["id"])
        self.update_start_button_state()

    def update_target_group_selector(self) -> None:
        """Update the target group selector based on the selected target catalog.

        The semantics are identical to :meth:`update_source_group_selector`,
        but applied to the target side.
        """
        self.target_group_selector.clear()
        cat = self.target_catalog_selector.currentData()
        if not cat:
            self.target_group_selector.addItem("<All Groups>", None)
        else:
            self.target_group_selector.addItem("<All Groups>", None)
            for g in get_groups_for_catalog(cat):
                self.target_group_selector.addItem(g["title"], g["id"])
        self.update_start_button_state()

    # --- Mapping process and result handling ------------------------------

    def start_mapping_process(self) -> None:
        """Start the many-to-many similarity process in a background task.

        This method:

        * Resets the result table and disables start/save buttons,
        * Logs the currently active embedding model,
        * Creates a :class:`BulkSimilarityTask` with the current configuration,
        * Connects its signals to local slots, and
        * Submits it to the global :class:`QThreadPool`.
        """
        self.status_output.clear()
        self.results_table.setRowCount(0)
        self.save_button.setEnabled(False)
        for w in (self.start_mapping_button, self.save_button):
            w.setEnabled(False)

        model_name = get_current_active_model_name() or "default"
        self.append_status(f"Model: {model_name}")

        task = BulkSimilarityTask(
            source_cat_uuid=self.source_catalog_selector.currentData(),
            source_grp_id=self.source_group_selector.currentData(),
            target_cat_uuid=self.target_catalog_selector.currentData(),
            target_grp_id=self.target_group_selector.currentData(),
            embedding_model_name=model_name,
            similarity_threshold=0.3,
            top_n_display=10000,
        )
        task.signals.progress.connect(self.append_status)
        task.signals.finished.connect(self.on_bulk_done)
        task.signals.error.connect(self.on_bulk_error)
        self.threadpool.start(task)

    def on_bulk_done(self, result: Dict[str, Any]) -> None:
        """Handle completion of the many-to-many similarity process.

        Args:
            result: Result dictionary returned by
                :func:`execute_many_to_many_similarity_process`. It is
                expected to contain a ``statistics`` sub-dict as well as
                a ``top_results`` list for UI display.
        """
        count = result.get("statistics", {}).get("relationships_written", 0)
        self.append_status(f"M-N finished: {count}")
        self.results_data = result.get("top_results", [])
        self._populate_results_table()
        self.save_button.setEnabled(bool(self.results_data))
        self.start_mapping_button.setEnabled(True)

    def on_bulk_error(self, msg: str) -> None:
        """Handle errors from the many-to-many background task.

        Args:
            msg: Error message emitted by :class:`BulkSimilarityTask`.
        """
        self.append_status(f"❌ {msg}")
        QMessageBox.critical(self, "Error", msg)
        self.start_mapping_button.setEnabled(True)

    def _populate_results_table(self) -> None:
        """Fill the results table with the current many-to-many result set.

        Each row corresponds to a single similarity relation between a
        source and a target control, including the computed similarity
        score and a category label (e.g. "high", "medium", "low").
        """
        self.results_table.setRowCount(0)
        rows = self.results_data or []
        self.results_table.setRowCount(len(rows))
        for i, e in enumerate(rows):
            vals = [
                e.get("source_control_id", ""),
                e.get("source_control_title", ""),
                e.get("target_control_id", ""),
                e.get("target_control_title", ""),
                f"{e.get('similarity_score', 0):.3f}",
                e.get("similarity_category", ""),
            ]
            for j, v in enumerate(vals):
                self.results_table.setItem(i, j, QTableWidgetItem(str(v)))
        self.results_table.resizeColumnsToContents()
        self.results_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )

    def _save_relations(self) -> None:
        """Persist selected similarity relations to Neo4j.

        The method filters the current result set according to two criteria:

        * The source control id must be present.
        * The similarity score must be at least ``0.3``.

        The user is asked for confirmation before
        :func:`store_similarity_relations` is called. On success, a small
        status message with the number of merged relationships is shown.
        """
        if not self.results_data:
            return

        to_save: List[Dict[str, Any]] = []
        model_name = get_current_active_model_name() or "default"

        for e in self.results_data:
            if not e.get("source_control_id") or e.get(
                "similarity_score", 0
            ) < 0.3:
                continue
            to_save.append(
                {
                    "source_control_id": e["source_control_id"],
                    "target_control_id": e["target_control_id"],
                    "similarity_score": e["similarity_score"],
                    "similarity_category": e.get("similarity_category", ""),
                    "model_name": model_name,
                }
            )

        if not to_save:
            QMessageBox.information(self, "Info", "No results ≥0.3 to save.")
            return

        if (
            QMessageBox.question(
                self,
                "Save",
                f"Save {len(to_save)} relationships?",
                QMessageBox.Yes | QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return

        self.append_status(f"Saving {len(to_save)} …")
        try:
            res = store_similarity_relations(to_save, model_name)
            merged = res.get("relationships_merged", 0)
            self.append_status(f"✅ {merged} saved.")
        except Exception as e:
            self.append_status(f"❌ {e}")
            QMessageBox.critical(
                self, "Error", f"Failed to save relationships:\n{str(e)}"
            )
            return

    # --- UI state / status helpers ---------------------------------------

    def update_start_button_state(self) -> None:
        """Enable or disable the start button based on current selections.

        The many-to-many process can only be started if both a source and
        a target catalog have been selected (group selection is optional).
        """
        source_catalog = bool(self.source_catalog_selector.currentData())
        target_catalog = bool(self.target_catalog_selector.currentData())
        self.start_mapping_button.setEnabled(source_catalog and target_catalog)

    def append_status(self, msg: str) -> None:
        """Append a status message to the status text area.

        The view automatically scrolls to the bottom so that the latest
        message remains visible.

        Args:
            msg: Text message to be appended.
        """
        self.status_output.append(msg)
        self.status_output.verticalScrollBar().setValue(
            self.status_output.verticalScrollBar().maximum()
        )

    def reload_catalog_data(self) -> None:
        """Reload catalog and group information and update the selectors.

        This method is typically triggered by the reload button. It calls
        :meth:`populate_catalog_selectors` and logs a short status message.
        """
        self.append_status("🔄 Reloading …")
        self.populate_catalog_selectors()
        self.append_status("✅ Reloaded")

    def closeEvent(self, event) -> None:
        """Handle the widget close event.

        Currently this method only logs a debug message and delegates to
        the base implementation. It is provided for symmetry with other
        views and as a hook for potential future cleanup logic.

        Args:
            event: The Qt close event instance.
        """
        log.debug("Closing ControlMappingMNView")
        super().closeEvent(event)