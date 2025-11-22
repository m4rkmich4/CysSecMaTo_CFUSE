# Filename: ui/control_mapping_1n_view.py
# Standalone 1-N Mapping View (purely for single-source to many-targets mapping)

"""
Qt view for performing 1-to-N control mappings.

This module defines a dedicated Qt-based view that supports the following flow:

1. The user selects a source catalog and (optionally) a group.
2. Controls from the selected source are loaded into a table.
3. A single source control is "locked" for comparison.
4. The user selects a target catalog and (optionally) a group.
5. A background task computes 1-N similarity scores against all eligible
   controls in the target selection.
6. Results are displayed in a table and can be persisted as similarity
   relations in the Neo4j graph.

The view is intentionally kept separate from other mapping UIs in order to
focus on the 1-to-N scenario (one source control to many potential targets).
"""

import logging
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QMessageBox,
    QSplitter
)
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject

from db.queries_embeddings import get_all_catalogs, get_groups_for_catalog
from logic.control_mapping import (
    prepare_locked_control_data,
    calculate_all_similarities,
    store_similarity_relations,
)
from logic.control_embedding import get_current_active_model_name

log = logging.getLogger(__name__)


# --- Background Task -----------------------------------------------------

class SingleMappingSignals(QObject):
    """Signal container for the 1-N mapping background task.

    This QObject encapsulates the Qt signals used by :class:`SingleMappingTask`
    to communicate with the GUI thread.

    Attributes:
        finished (Signal): Emitted when the mapping task completes
            successfully. Carries a list of result dictionaries.
        error (Signal): Emitted when an error occurs in the background
            task. Carries an error message string.
        progress (Signal): Emitted to report intermediate status messages
            during the 1-N computation.
    """
    finished = Signal(list)
    error    = Signal(str)
    progress = Signal(str)


class SingleMappingTask(QRunnable):
    """QRunnable that performs 1-to-N similarity calculation in the background.

    The task takes a single locked source control and computes similarities
    against all eligible target controls from the selected catalog (and
    optional group). Results are returned to the GUI via Qt signals.

    Args:
        locked_data: Dictionary describing the locked source control
            (typically created by :func:`prepare_locked_control_data`).
        catalog_uuid: UUID of the target catalog whose controls should be
            considered as mapping candidates.
        group_id: Optional group identifier for restricting the target
            selection. If ``None``, all groups (or top-level controls)
            may be considered depending on the underlying logic.
        display_threshold: Minimum similarity score above which results
            should be kept for display. Filtering is delegated to
            :func:`calculate_all_similarities`.
    """
    def __init__(
        self,
        locked_data: Dict[str, Any],
        catalog_uuid: str,
        group_id: Optional[str],
        display_threshold: float = 0.0
    ):
        super().__init__()
        self.signals = SingleMappingSignals()
        self.locked_data       = locked_data
        self.catalog_uuid      = catalog_uuid
        self.group_id          = group_id
        self.display_threshold = display_threshold

    def run(self):
        """Execute the 1-N similarity calculation.

        This method is executed in a worker thread managed by the global
        :class:`QThreadPool`. It delegates the actual computation to
        :func:`calculate_all_similarities` and emits signals for progress,
        success and error handling.
        """
        self.signals.progress.emit("Starting 1-N similarity calculation…")
        try:
            results = calculate_all_similarities(
                locked_control_data  = self.locked_data,
                target_catalog_uuid  = self.catalog_uuid,
                target_group_id      = self.group_id,
                display_threshold    = self.display_threshold
            )
            self.signals.finished.emit(results)
            self.signals.progress.emit(
                f"1-N finished ({len(results)} ≥ {self.display_threshold})."
            )
        except Exception as e:
            log.error("Error in SingleMappingTask:", exc_info=True)
            self.signals.error.emit(str(e))


# --- Main View -----------------------------------------------------------

class ControlMapping1NView(QWidget):
    """Qt widget implementing the 1-to-N control mapping workflow.

    The widget provides a two-pane layout:

    * Left pane: selection of a source catalog, optional group, and a table
      of available source controls. A single control can be "locked" as the
      basis for all 1-N comparisons.
    * Right pane: selection of a target catalog and optional group.

    Below the main splitter, the widget offers:

    * Buttons to start the 1-N similarity computation and save the resulting
      relations.
    * A result table showing target controls with similarity scores.
    * A status text area for progress and error messages.

    All long-running operations (similarity computation and database writes)
    are encapsulated in background tasks or utility functions; the view
    focuses on orchestration and user interaction.
    """
    def __init__(self):
        """Initialize the 1-N mapping view and set up the UI layout."""
        super().__init__()
        self.setObjectName("ControlMapping1NView")
        self.setMinimumWidth(1000)
        self.threadpool           = QThreadPool.globalInstance()

        # In-memory state for the current session
        self.catalogs             = []   # type: List[Dict[str,Any]]
        self.locked_control_data  = None # type: Optional[Dict[str,Any]]
        self.results_data         = []   # type: List[Dict[str,Any]]

        # --- UI Elements ---
        # Source side (step 1: choose and lock control)
        self.source_catalog_selector = QComboBox()
        self.source_group_selector   = QComboBox()
        self.load_source_button      = QPushButton("Load")
        self.reload_button           = QPushButton("🔁")
        self.reload_button.setToolTip("Reload catalog/group list")

        self.source_table = QTableWidget(0,2)
        self.source_table.setHorizontalHeaderLabels(["Control-ID","Title"])
        self.source_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.source_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.source_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.source_table.setSelectionMode(QTableWidget.SingleSelection)
        self.source_table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.lock_button          = QPushButton("Lock")
        self.unlock_button        = QPushButton("Unlock")
        self.unlock_button.setVisible(False)
        self.lock_button.setEnabled(False)

        self.locked_info_label    = QLabel("Locked: -")
        self.locked_prose_display = QTextEdit()
        self.locked_prose_display.setReadOnly(True)
        self.locked_prose_display.setMaximumHeight(80)
        self.locked_prose_display.setVisible(False)

        # Target side (step 2: select catalog/group for mapping)
        self.target_catalog_selector = QComboBox()
        self.target_group_selector   = QComboBox()
        self.start_mapping_button    = QPushButton("Start")
        self.start_mapping_button.setEnabled(False)

        # Save button for persisting mapping relations
        self.save_button = QPushButton("Save")
        self.save_button.setEnabled(False)

        # Result table showing 1-N mapping candidates
        self.results_table = QTableWidget(0,6)
        self.results_table.setHorizontalHeaderLabels([
            "Source","Source-ID","Target-ID","Target Title","Score","Category"
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)

        # Status output area for progress messages and logs
        self.status_output = QTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setMaximumHeight(150)

        # --- Layout ---
        main_lay = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        # left panel (source)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("1. Source"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Catalog:"))
        row.addWidget(self.source_catalog_selector,1)
        row.addWidget(QLabel("Group:"))
        row.addWidget(self.source_group_selector,1)
        row.addWidget(self.load_source_button)
        row.addWidget(self.reload_button)
        ll.addLayout(row)
        ll.addWidget(self.source_table)
        hl = QHBoxLayout()
        hl.addWidget(self.lock_button)
        hl.addWidget(self.unlock_button)
        hl.addStretch()
        hl.addWidget(self.locked_info_label)
        ll.addLayout(hl)
        ll.addWidget(self.locked_prose_display)
        splitter.addWidget(left)

        # right panel (target)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("2. Target"))
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Catalog:"))
        row2.addWidget(self.target_catalog_selector,1)
        row2.addWidget(QLabel("Group:"))
        row2.addWidget(self.target_group_selector,1)
        rl.addLayout(row2)
        rl.addStretch()
        splitter.addWidget(right)

        main_lay.addWidget(splitter)

        # Control buttons row (start mapping + save)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self.start_mapping_button)
        btns.addWidget(self.save_button)
        btns.addStretch()
        main_lay.addLayout(btns)

        # Results + status area
        main_lay.addWidget(QLabel("Results"))
        main_lay.addWidget(self.results_table,1)
        main_lay.addWidget(QLabel("Status"))
        main_lay.addWidget(self.status_output)

        # --- Signals ---
        self.reload_button.clicked.connect(self.reload_catalog_data)
        self.load_source_button.clicked.connect(self.load_source_controls)
        self.source_catalog_selector.currentIndexChanged.connect(self.update_source_group_selector)
        self.source_table.itemSelectionChanged.connect(self.on_source_selection_changed)
        self.lock_button.clicked.connect(self.lock_selection)
        self.unlock_button.clicked.connect(self.unlock_selection)
        self.target_catalog_selector.currentIndexChanged.connect(self.update_target_group_selector)
        self.target_group_selector.currentIndexChanged.connect(self.update_start_button_state)
        self.start_mapping_button.clicked.connect(self.start_mapping_process)
        self.save_button.clicked.connect(self._save_relations)

        # Initial population of catalog selectors
        self.populate_catalog_selectors()

    # --- Methods identical to your previous 1-N code ---

    def populate_catalog_selectors(self):
        """Load all catalogs and fill source/target catalog selectors.

        This method retrieves all catalogs via :func:`get_all_catalogs` and
        populates both the source and target selectors. The current
        selections are preserved where possible.
        """
        try:
            self.catalogs = get_all_catalogs()
            s_cur = self.source_catalog_selector.currentData()
            t_cur = self.target_catalog_selector.currentData()

            self.source_catalog_selector.blockSignals(True)
            self.target_catalog_selector.blockSignals(True)

            self.source_catalog_selector.clear()
            self.target_catalog_selector.clear()
            self.source_catalog_selector.addItem("<Select Catalog>", None)
            self.target_catalog_selector.addItem("<Select Catalog>", None)

            for cat in self.catalogs:
                self.source_catalog_selector.addItem(cat["title"], cat["uuid"])
                self.target_catalog_selector.addItem(cat["title"], cat["uuid"])

            if s_cur:
                idx = self.source_catalog_selector.findData(s_cur)
                if idx >= 0:
                    self.source_catalog_selector.setCurrentIndex(idx)
            if t_cur:
                idx = self.target_catalog_selector.findData(t_cur)
                if idx >= 0:
                    self.target_catalog_selector.setCurrentIndex(idx)

        finally:
            # Always re-enable signals and update dependent selectors.
            self.source_catalog_selector.blockSignals(False)
            self.target_catalog_selector.blockSignals(False)
            self.update_source_group_selector()
            self.update_target_group_selector()

    def update_source_group_selector(self):
        """Update the group selector for the currently selected source catalog.

        If no catalog is selected, only a placeholder entry is shown. When
        a catalog is chosen, all groups for that catalog are loaded via
        :func:`get_groups_for_catalog`.
        """
        self.source_group_selector.clear()
        cat = self.source_catalog_selector.currentData()
        if not cat:
            self.source_group_selector.addItem("<All Groups>", None)
        else:
            self.source_group_selector.addItem("<All Groups>", None)
            for g in get_groups_for_catalog(cat):
                self.source_group_selector.addItem(g["title"], g["id"])
        # No selection yet -> locking is disabled until a row is selected.
        self.lock_button.setEnabled(False)

    def update_target_group_selector(self):
        """Update the group selector for the currently selected target catalog.

        If no catalog is selected, only a placeholder entry is provided.
        Otherwise, all groups from the selected target catalog are loaded.
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

    def load_source_controls(self):
        """Load source controls for the selected catalog/group into the table.

        The controls are retrieved using
        ``db.queries_embeddings.get_controls_with_description_parts`` via
        a dynamic import and displayed in the left-hand source table. Each
        row keeps the full record as ``Qt.UserRole`` data on the first
        column, which is later used when locking a control.
        """
        self.source_table.setRowCount(0)
        cat = self.source_catalog_selector.currentData()
        grp = self.source_group_selector.currentData()
        if not cat:
            QMessageBox.warning(self, "Error", "Please select source catalog.")
            return
        self.append_status(f"Loading Controls for {cat} …")
        data = __import__("db.queries_embeddings", fromlist=["get_controls_with_description_parts"]) \
               .get_controls_with_description_parts(
                    catalog_uuid=cat,
                    group_id=grp,
                    show_all_controls=(grp is None)
               )
        self.source_table.setRowCount(len(data))
        for i, e in enumerate(data):
            it = QTableWidgetItem(e["control_id"])
            it.setData(Qt.UserRole, e)
            self.source_table.setItem(i, 0, it)
            self.source_table.setItem(i, 1, QTableWidgetItem(e["control_title"]))
        self.source_table.resizeColumnsToContents()

    def on_source_selection_changed(self):
        """React to changes in the selection of the source control table.

        This method simply enables or disables the *Lock* button depending
        on whether a row is currently selected.
        """
        valid = bool(self.source_table.selectedItems())
        self.lock_button.setEnabled(valid)

    def lock_selection(self):
        """Lock the currently selected source control for 1-N mapping.

        The selected row from the source table is used to build a
        ``locked_control_data`` structure via
        :func:`prepare_locked_control_data`. Once locked, the source
        catalog/group selection and table are disabled to avoid changing
        the source context mid-computation.
        """
        rows = self.source_table.selectionModel().selectedRows()
        if not rows:
            return
        data = self.source_table.item(rows[0].row(), 0).data(Qt.UserRole)
        ld = prepare_locked_control_data(
            part_element_id = data["part_element_id"],
            control_id      = data["control_id"],
            control_title   = data["control_title"],
            control_prose   = data["description"]
        )
        self.locked_control_data = ld
        self.locked_info_label.setText(f"Locked: <b>{ld['control_id']}</b>")
        self.locked_prose_display.setPlainText(ld["prose"])
        self.locked_prose_display.setVisible(True)
        self.unlock_button.setVisible(True)
        self.lock_button.setEnabled(False)
        # Disable source-related widgets while a control is locked.
        for w in (
            self.source_catalog_selector,
            self.source_group_selector,
            self.load_source_button,
            self.source_table
        ):
            w.setEnabled(False)
        # Mapping can only be started if a target catalog is selected.
        self.start_mapping_button.setEnabled(bool(self.target_catalog_selector.currentData()))

    def unlock_selection(self):
        """Unlock the current source control and re-enable source selection.

        This clears the locked state and re-enables source selectors and
        the source table. The user can then select another source control
        for 1-N mapping.
        """
        self.locked_control_data = None
        self.locked_info_label.setText("Locked: -")
        self.locked_prose_display.clear()
        self.locked_prose_display.setVisible(False)
        self.unlock_button.setVisible(False)
        for w in (
            self.source_catalog_selector,
            self.source_group_selector,
            self.load_source_button,
            self.source_table
        ):
            w.setEnabled(True)
        self.save_button.setEnabled(False)
        self.start_mapping_button.setEnabled(False)
        if self.source_table.selectedItems():
            self.lock_button.setEnabled(True)

    def start_mapping_process(self):
        """Start the 1-N similarity computation as a background task.

        The method resets the results table and disables relevant buttons.
        If no source control is currently locked, an error message is
        shown. Otherwise, a :class:`SingleMappingTask` is created and
        submitted to the global :class:`QThreadPool`.
        """
        self.status_output.clear()
        self.results_table.setRowCount(0)
        self.save_button.setEnabled(False)
        # Disable controls while the background task is running.
        for w in (
            self.start_mapping_button,
            self.save_button,
            self.load_source_button,
            self.lock_button,
            self.unlock_button
        ):
            w.setEnabled(False)
        if not self.locked_control_data:
            QMessageBox.warning(self, "Error", "Please lock a source control for 1-N comparison.")
            self.start_mapping_button.setEnabled(True)
            self.unlock_button.setEnabled(True)
            return

        task = SingleMappingTask(
            locked_data       = self.locked_control_data,
            catalog_uuid      = self.target_catalog_selector.currentData(),
            group_id          = self.target_group_selector.currentData(),
            display_threshold = 0.0
        )
        task.signals.progress.connect(self.append_status)
        task.signals.finished.connect(self.on_single_done)
        task.signals.error.connect(self.on_single_error)
        self.threadpool.start(task)

    def on_single_done(self, results: List[Dict[str,Any]]):
        """Handle successful completion of the 1-N mapping task.

        Args:
            results: List of dictionaries describing the similarity
                results returned by :func:`calculate_all_similarities`.
        """
        self.append_status(f"1-N finished: {len(results)}")
        self.results_data = results
        self._populate_results_table()
        self.save_button.setEnabled(bool(results))
        self.start_mapping_button.setEnabled(True)
        self.unlock_button.setEnabled(True)

    def on_single_error(self, msg: str):
        """Handle errors emitted by the 1-N mapping background task.

        Args:
            msg: Human-readable error message describing the failure
                that occurred in the worker thread.
        """
        self.append_status(f"❌ {msg}")
        QMessageBox.critical(self, "Error", msg)
        self.start_mapping_button.setEnabled(True)
        self.unlock_button.setEnabled(True)

    def _populate_results_table(self):
        """Populate the results table using the current results data.

        The table shows information about the locked source control,
        each target control candidate, its similarity score and an
        optional similarity category label.
        """
        self.results_table.setRowCount(0)
        rows = self.results_data or []
        self.results_table.setRowCount(len(rows))
        for i, e in enumerate(rows):
            vals = [
                self.locked_control_data.get("control_id", "") if self.locked_control_data else "",
                self.locked_control_data.get("title", e.get("source_control_prose","")[:50]+"...") if self.locked_control_data else e.get("source_control_prose","")[:50]+"...",
                e.get("target_control_id",""),
                e.get("target_control_title",""),
                f"{e.get('similarity_score',0):.3f}",
                e.get("similarity_category","")
            ]
            for j, v in enumerate(vals):
                self.results_table.setItem(i, j, QTableWidgetItem(str(v)))
        self.results_table.resizeColumnsToContents()
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    def _save_relations(self):
        """Persist selected 1-N similarity relations to the database.

        The method filters current results by a minimum similarity score
        (here: 0.3) and prepares a list of relationship records. The user is
        asked for confirmation, and on approval, the records are written
        via :func:`store_similarity_relations`.

        If no results meet the threshold, an informational message is
        shown and nothing is saved.
        """
        if not self.results_data:
            return
        to_save = []
        model_name = get_current_active_model_name() or "default"

        for e in self.results_data:
            if not self.locked_control_data:
                log.warning("Cannot save 1-N relations: no control locked.")
                QMessageBox.warning(self, "Warning", "No source control is locked for 1-N saving.")
                return
            source_id = self.locked_control_data.get("control_id")
            if not source_id or e.get("similarity_score",0) < 0.3:
                continue
            to_save.append({
                "source_control_id": source_id,
                "target_control_id": e["target_control_id"],
                "similarity_score": e["similarity_score"],
                "similarity_category": e.get("similarity_category",""),
                "model_name": model_name
            })

        if not to_save:
            QMessageBox.information(self, "Info", "No results ≥0.3 to save.")
            return

        if QMessageBox.question(
                self, "Save", f"Save {len(to_save)} relationships?",
                QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return

        self.append_status(f"Saving {len(to_save)} …")
        try:
            res = store_similarity_relations(to_save, model_name)
            merged = res.get("relationships_merged", 0)
            self.append_status(f"✅ {merged} saved.")
        except Exception as e:
            self.append_status(f"❌ {e}")
            QMessageBox.critical(self, "Error", f"Failed to save relationships:\n{str(e)}")
            return

        if self.source_table.selectedItems():
            self.lock_button.setEnabled(True)
        self.unlock_button.setEnabled(True)

    def update_start_button_state(self):
        """Enable or disable the *Start* button based on current state.

        The 1-N mapping can only be started if a target catalog is
        selected *and* a source control is currently locked.
        """
        ok = bool(self.target_catalog_selector.currentData()) and bool(self.locked_control_data)
        self.start_mapping_button.setEnabled(ok)

    def append_status(self, msg: str):
        """Append a status message to the status output area.

        The text view automatically scrolls to the bottom so that the
        most recent messages are always visible.

        Args:
            msg: Text message to append to the status widget.
        """
        self.status_output.append(msg)
        self.status_output.verticalScrollBar().setValue(self.status_output.verticalScrollBar().maximum())

    def reload_catalog_data(self):
        """Reload catalog data and refresh the selectors.

        This is a convenience wrapper that logs the operation in the
        status area and then calls :meth:`populate_catalog_selectors`.
        """
        self.append_status("🔄 Reloading …")
        self.populate_catalog_selectors()
        self.append_status("✅ Reloaded")

    def closeEvent(self, event):
        """Handle the widget close event.

        The method logs a debug message and then delegates to the
        base implementation.
        """
        log.debug("Closing ControlMapping1NView")
        super().closeEvent(event)