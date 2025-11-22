# Filename: ui/rag_mapping_view.py
# Location: /Users/michaelmark/PycharmProjects/CySecMaTo/ui/rag_mapping_view.py
# NEW FILE for the RAG Mapping View

import logging
from typing import Optional, Dict, Any, List, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QMessageBox,
    QSplitter, QFrame, QApplication # QApplication for clipboard
)
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject
from PySide6.QtGui import QAction # For context menu

# Database functions for Catalog/Group selection
from db.queries_embeddings import get_all_catalogs, get_groups_for_catalog
# Logic functions for RAG and preparation
from logic.rag_processor import fetch_similar_controls_for_rag, generate_llm_comparison, save_confirmed_mapping
from logic.control_mapping import prepare_locked_control_data
# Optionally import function to fetch controls for the source table
# Assumption: We use the same function here as the MappingView to display the source
from db.queries_embeddings import get_controls_with_description_parts

log = logging.getLogger(__name__)

# --- Worker for background tasks ---

class FetchSimilarControlsSignals(QObject):
    """Signals for the task that fetches similar controls."""
    finished = Signal(list) # Sends the list of result dicts
    error = Signal(str)
    progress = Signal(str)

class FetchSimilarControlsTask(QRunnable):
    """Task to fetch similar controls based on HAS_SIMILARITY."""
    def __init__(self, source_control_id: str):
        super().__init__()
        self.signals = FetchSimilarControlsSignals()
        self.source_control_id = source_control_id

    def run(self):
        self.signals.progress.emit(f"Searching for similar controls for {self.source_control_id}...")
        try:
            # Call logic (which calls the DB function)
            # We could add filters for categories/limit here
            results = fetch_similar_controls_for_rag(self.source_control_id)
            self.signals.finished.emit(results)
        except Exception as e:
            log.error(f"Error in FetchSimilarControlsTask for {self.source_control_id}: {e}", exc_info=True)
            self.signals.error.emit(f"Error fetching similar controls: {str(e)}")

class LLMComparisonSignals(QObject):
    """Signals for the LLM comparison task."""
    finished = Signal(tuple) # Sends tuple (Classification | None, Explanation)
    error = Signal(str)
    progress = Signal(str)

class LLMComparisonTask(QRunnable):
    """Task for calling the LLM for control comparison."""
    def __init__(self, source_prose: str, target_prose: str):
        super().__init__()
        self.signals = LLMComparisonSignals()
        self.source_prose = source_prose
        self.target_prose = target_prose

    def run(self):
        self.signals.progress.emit("Sending request to LLM...")
        try:
            # Call logic
            classification, explanation = generate_llm_comparison(self.source_prose, self.target_prose)
            self.signals.finished.emit((classification, explanation)) # Send as tuple
        except Exception as e:
            log.error(f"Error in LLMComparisonTask: {e}", exc_info=True)
            self.signals.error.emit(f"Error during LLM request: {str(e)}")

# Optional: Worker for saving (currently implemented synchronously)


# --- Main View Class ---

class RAGMappingView(QWidget):
    """
    Qt view for the RAG-based control mapping process.
    """
    def __init__(self):
        super().__init__()
        self.setObjectName("RAGMappingView")
        self.setMinimumWidth(1000)

        # ThreadPool
        self.threadpool = QThreadPool.globalInstance()

        # Data storage
        self.catalogs: List[Dict[str, Any]] = []
        self.source_controls_data: List[Dict[str, Any]] = [] # For left table
        self.locked_control_data: Optional[Dict[str, Any]] = None # Contains source incl. prose/embedding
        self.similar_controls_data: List[Dict[str, Any]] = [] # For right table (Similar ones)
        self.selected_target_control_data: Optional[Dict[str, Any]] = None # Selected target from right table
        self.current_llm_result: Optional[Dict[str, Any]] = None # Holds classification + explanation

        # --- UI Elements ---

        # Area 1: Select and lock source (similar to MappingView)
        self.source_catalog_selector = QComboBox()
        self.source_group_selector = QComboBox()
        self.load_source_button = QPushButton("Load")
        self.reload_button = QPushButton("🔁") # Also useful here
        self.reload_button.setToolTip("Reload catalog and group lists")
        self.source_table = QTableWidget()
        self.source_table.setColumnCount(2)
        self.source_table.setHorizontalHeaderLabels(["Control-ID", "Title"])
        self.source_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.source_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.source_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.source_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.source_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.lock_button = QPushButton("Lock Selection (Source)")
        self.unlock_button = QPushButton("Unlock Selection")
        self.locked_info_label = QLabel("Locked Control: -")
        self.locked_prose_display = QTextEdit()
        self.locked_prose_display.setReadOnly(True)
        self.locked_prose_display.setMaximumHeight(80)
        self.locked_prose_display.setPlaceholderText("Description of the locked control...")
        self.locked_prose_display.setVisible(False)
        self.lock_button.setEnabled(False)
        self.unlock_button.setVisible(False)

        # Area 2: Display and select similar controls
        self.similar_controls_table = QTableWidget()
        self.similar_controls_table.setColumnCount(6) # ID, Title, Prose (Excerpt), Score, Category, Mapped?
        self.similar_controls_table.setHorizontalHeaderLabels([
             "Similar Control ID", "Title", "Description", "Score", "Category", "Mapped?" # Column for mapping status
        ])
        self.similar_controls_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.similar_controls_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.similar_controls_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Adjust column widths
        self.similar_controls_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch) # Prose
        self.similar_controls_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # ID
        self.similar_controls_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Title
        self.similar_controls_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # Score
        self.similar_controls_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Category
        self.similar_controls_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents) # Mapped?

        # Area 3: LLM interaction and saving
        self.compare_button = QPushButton("Compare Selected Control with LLM")
        self.compare_button.setEnabled(False) # Activate when target is selected
        self.llm_output_display = QTextEdit()
        self.llm_output_display.setReadOnly(True)
        self.llm_output_display.setPlaceholderText("Explanation and classification from LLM...")
        self.save_mapping_button = QPushButton("Save Mapping")
        self.save_mapping_button.setEnabled(False) # Activate when LLM result is available

        # Area 4: Status
        self.status_output = QTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setMaximumHeight(100) # A bit smaller

        # === Layout ===
        main_layout = QVBoxLayout(self)

        # Top: Select/lock source
        source_selection_widget = QWidget()
        source_selection_layout = QVBoxLayout(source_selection_widget)
        source_selection_layout.addWidget(QLabel("1. Select and lock source control:"))
        hl_src = QHBoxLayout()
        hl_src.addWidget(QLabel("Catalog:")); hl_src.addWidget(self.source_catalog_selector, 1)
        hl_src.addWidget(QLabel("Group:")); hl_src.addWidget(self.source_group_selector, 1)
        hl_src.addWidget(self.load_source_button); hl_src.addWidget(self.reload_button)
        source_selection_layout.addLayout(hl_src)
        source_selection_layout.addWidget(self.source_table, 1) # Table can grow
        hl_lock = QHBoxLayout()
        hl_lock.addWidget(self.lock_button); hl_lock.addWidget(self.unlock_button)
        hl_lock.addWidget(self.locked_info_label, 1, Qt.AlignmentFlag.AlignRight)
        source_selection_layout.addLayout(hl_lock)
        source_selection_layout.addWidget(self.locked_prose_display) # Display prose

        # Middle: Display similar controls / LLM interaction
        middle_splitter = QSplitter(Qt.Orientation.Vertical)

        similar_widget = QWidget()
        similar_layout = QVBoxLayout(similar_widget)
        similar_layout.addWidget(QLabel("2. Similar Controls (from :HAS_SIMILARITY):"))
        similar_layout.addWidget(self.similar_controls_table, 1) # Table can grow
        similar_layout.addWidget(self.compare_button)
        middle_splitter.addWidget(similar_widget)

        llm_widget = QWidget()
        llm_layout = QVBoxLayout(llm_widget)
        llm_layout.addWidget(QLabel("3. LLM Analysis and Mapping:"))
        llm_layout.addWidget(self.llm_output_display, 1) # Text field can grow
        llm_layout.addWidget(self.save_mapping_button)
        middle_splitter.addWidget(llm_widget)

        middle_splitter.setSizes([400, 200]) # Initial sizes for splitter

        # Assemble main layout
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(source_selection_widget)
        main_splitter.addWidget(middle_splitter)
        main_splitter.setSizes([500, 500]) # Initial sizes

        main_layout.addWidget(main_splitter, 1) # Splitter gets most space
        main_layout.addWidget(QLabel("Status:"))
        main_layout.addWidget(self.status_output)

        # === Connect Signals ===
        self.load_source_button.clicked.connect(self.load_source_controls)
        self.reload_button.clicked.connect(self.reload_catalog_data)
        self.source_catalog_selector.currentIndexChanged.connect(self.update_source_group_selector)
        self.source_table.itemSelectionChanged.connect(self.on_source_selection_changed)
        self.lock_button.clicked.connect(self.lock_selection)
        self.unlock_button.clicked.connect(self.unlock_selection)
        # Signal for selection in the *similarity* table
        self.similar_controls_table.itemSelectionChanged.connect(self.on_target_selection_changed)
        # Button to start LLM comparison
        self.compare_button.clicked.connect(self.request_llm_comparison)
        # Button to save mapping
        self.save_mapping_button.clicked.connect(self.save_mapping)


        # === Initialization ===
        self.populate_catalog_selectors()


    # --- Placeholder / Basic Methods ---

    def append_status(self, msg: str):
        """Appends a message to the status text field."""
        try:
            self.status_output.append(msg)
            self.status_output.verticalScrollBar().setValue(self.status_output.verticalScrollBar().maximum())
        except Exception as e:
             log.error(f"Error appending status message: {e}", exc_info=True)

    def _populate_group_selector(self, selector: QComboBox, catalog_uuid: Optional[str]):
        # (Code as in ControlMappingView)
        current = selector.currentData()
        selector.clear()
        if not catalog_uuid: selector.addItem("<Select Catalog>", None); return
        try:
            groups = get_groups_for_catalog(catalog_uuid)
            selector.addItem("<All Groups>", None); idx = 0
            for i, g in enumerate(groups):
                selector.addItem(g['title'], g['id'])
                if g['id'] == current: idx = i + 1
            selector.setCurrentIndex(idx)
        except Exception as e:
             self.append_status(f"❌ Error loading groups: {e}"); log.error(f"Error loading groups for {catalog_uuid}:", exc_info=True)
             selector.addItem("<Error>", None)

    def populate_catalog_selectors(self):
        # (Code as in ControlMappingView)
        log.debug("Populating catalog selectors for RAG View...")
        try:
            self.catalogs = get_all_catalogs()
            current_uuid = self.source_catalog_selector.currentData() # Only source relevant
            self.source_catalog_selector.blockSignals(True)
            self.source_catalog_selector.clear(); self.source_catalog_selector.addItem("<Select Catalog>", None)
            selected_index = 0
            for i, cat in enumerate(self.catalogs):
                self.source_catalog_selector.addItem(cat['title'], cat['uuid'])
                if cat['uuid'] == current_uuid: selected_index = i + 1
            if selected_index < self.source_catalog_selector.count(): self.source_catalog_selector.setCurrentIndex(selected_index)
            self.source_catalog_selector.blockSignals(False)
            # Manually trigger update if index didn't change but should have options
            if self.source_catalog_selector.currentIndex() >=0 : self.update_source_group_selector()
            log.debug("Catalog selectors populated.")
        except Exception as e:
             self.append_status(f"❌ Error loading catalogs: {e}"); log.error("Error loading catalogs:", exc_info=True)
             QMessageBox.critical(self, "Error", f"Error loading catalog list:\n{e}")

    def update_source_group_selector(self):
        # (Code as in ControlMappingView)
        log.debug("Updating source groups...")
        uuid = self.source_catalog_selector.currentData()
        self._populate_group_selector(self.source_group_selector, uuid)
        self.lock_button.setEnabled(False) # Reset selection
        log.debug("Source groups updated.")

    def load_source_controls(self):
        # (Code as in ControlMappingView, uses get_controls_with_description_parts)
        self.source_table.setRowCount(0); self.source_controls_data = []; self.lock_button.setEnabled(False)
        source_uuid = self.source_catalog_selector.currentData()
        source_group_id = self.source_group_selector.currentData()
        if not source_uuid: QMessageBox.warning(self, "No Catalog", "Please select source catalog."); return
        self.append_status(f"Loading source controls for '{self.source_catalog_selector.currentText()}'...")
        try:
            # We need the function here that provides us with Controls *with* description Part
            from db.queries_embeddings import get_controls_with_description_parts
            data = get_controls_with_description_parts(catalog_uuid=source_uuid, group_id=source_group_id, show_all_controls=(source_group_id is None))
            self.source_controls_data = data
            self.append_status(f"{len(self.source_controls_data)} source controls loaded.")
            self.source_table.setRowCount(len(data))
            for i, entry in enumerate(data):
                 item_id = QTableWidgetItem(entry.get("control_id", "")); item_id.setData(Qt.ItemDataRole.UserRole, entry)
                 self.source_table.setItem(i, 0, item_id)
                 self.source_table.setItem(i, 1, QTableWidgetItem(entry.get("control_title", "")))
        except Exception as e:
             self.append_status(f"❌ Error loading source controls: {e}"); logging.error("Error in load_source_controls:", exc_info=True)
             QMessageBox.critical(self, "Error", f"Error loading source controls:\n{e}")
        finally:
             self.source_table.resizeColumnsToContents()
             if self.source_table.columnCount() > 1: self.source_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def on_source_selection_changed(self):
        selected_items = self.source_table.selectedItems()
        self.lock_button.setEnabled(len(selected_items) > 0 and self.locked_control_data is None)

    def lock_selection(self):
        # (Code as in ControlMappingView, calls prepare_locked_control_data)
        # IMPORTANT: After successful locking, call the fetch for similar controls!
        selected_rows = self.source_table.selectionModel().selectedRows()
        if not selected_rows: return
        item_with_data = self.source_table.item(selected_rows[0].row(), 0)
        if not item_with_data: return
        item_data = item_with_data.data(Qt.ItemDataRole.UserRole)
        required_keys = ["part_element_id", "control_id", "control_title", "description"]
        if not item_data or not all(key in item_data and item_data[key] is not None for key in required_keys):
             missing = [key for key in required_keys if not item_data or key not in item_data or item_data[key] is None]
             QMessageBox.critical(self, "Error", f"Selected control has missing data: {', '.join(missing)}."); return
        self.append_status(f"Attempting to lock control '{item_data.get('control_id')}'...")
        try:
             self.locked_control_data = prepare_locked_control_data(
                 part_element_id=item_data["part_element_id"], control_id=item_data["control_id"],
                 control_title=item_data["control_title"], control_prose=item_data["description"]
             )
             if self.locked_control_data:
                 locked_id = self.locked_control_data['control_id']; locked_title = self.locked_control_data['title']
                 locked_prose = self.locked_control_data.get('prose', ''); self.locked_info_label.setText(f"Locked Control: <b>{locked_id}</b> ({locked_title})")
                 self.locked_prose_display.setPlainText(locked_prose); self.locked_prose_display.setVisible(True)
                 self.lock_button.setEnabled(False); self.unlock_button.setVisible(True)
                 self.source_catalog_selector.setEnabled(False); self.source_group_selector.setEnabled(False)
                 self.load_source_button.setEnabled(False); self.source_table.setEnabled(False)
                 self.append_status(f"✅ Control '{locked_id}' locked. Fetching similar controls...")
                 # --- Trigger fetch of similar controls ---
                 self.fetch_and_display_similar_controls()
             else:
                 self.append_status("❌ Locking failed (Embedding not found?).")
                 QMessageBox.warning(self, "Error", "Embedding for selected control not loaded.")
        except Exception as e:
             self.locked_control_data = None; self.append_status(f"❌ Error during locking: {e}"); logging.error("Error in lock_selection:", exc_info=True)
             QMessageBox.critical(self, "Error", f"Error during locking:\n{e}")

    def unlock_selection(self):
        # (Code as in ControlMappingView, also clears similar controls table)
        self.locked_control_data = None; self.locked_info_label.setText("Locked Control: -")
        self.locked_prose_display.clear(); self.locked_prose_display.setVisible(False)
        self.unlock_button.setVisible(False); self.on_source_selection_changed()
        self.source_catalog_selector.setEnabled(True); self.source_group_selector.setEnabled(True)
        self.load_source_button.setEnabled(True); self.source_table.setEnabled(True)
        self.compare_button.setEnabled(False) # Reset LLM button
        self.save_mapping_button.setEnabled(False) # Reset Save button
        self.similar_controls_table.setRowCount(0); self.similar_controls_data = [] # Reset similar controls
        self.llm_output_display.clear() # Reset LLM output
        self.current_llm_result = None
        self.append_status("ℹ️ Lock released.")

    # --- NEW methods for RAG ---
    def fetch_and_display_similar_controls(self):
        """ Starts the task to fetch similar controls. """
        if not self.locked_control_data: return

        source_id = self.locked_control_data['control_id']
        self.similar_controls_table.setRowCount(0) # Delete old results
        self.similar_controls_data = []
        self.llm_output_display.clear() # Also delete LLM Output
        self.compare_button.setEnabled(False)
        self.save_mapping_button.setEnabled(False)
        self.current_llm_result = None
        self.append_status(f"Searching for similar controls for {source_id}...")

        # TODO: Fetch filter options for categories/limit from UI here, if desired
        # e.g. self.rag_category_selector.currentData(), self.rag_limit_spinbox.value()
        allowed_categories = None # Uses default ["high_similarity", "medium_similarity"]
        limit = None              # Uses default 5

        task = FetchSimilarControlsTask(source_control_id=source_id)
        # Assumption: We also need signals here like with MappingTask
        # Do we define them above or reuse MappingSignals? Own ones are cleaner.
        task.signals.progress.connect(self.append_status)
        task.signals.finished.connect(self.on_fetch_similar_done)
        task.signals.error.connect(self.on_fetch_similar_error)
        self.threadpool.start(task)

    def on_fetch_similar_done(self, similar_controls: List[Dict[str, Any]]):
        """ Populates the table with similar controls. """
        self.append_status(f"{len(similar_controls)} similar controls found.")
        self.similar_controls_data = similar_controls
        self.similar_controls_table.setRowCount(len(similar_controls))
        for i, entry in enumerate(similar_controls):
            item_id = QTableWidgetItem(entry.get("target_id", ""))
            # Store the whole dict in the item for easy access
            item_id.setData(Qt.ItemDataRole.UserRole, entry)
            self.similar_controls_table.setItem(i, 0, item_id)
            self.similar_controls_table.setItem(i, 1, QTableWidgetItem(entry.get("target_title", "")))
            prose = entry.get("target_prose", "")
            prose_snippet = (prose[:80] + '...') if len(prose) > 80 else prose
            prose_item = QTableWidgetItem(prose_snippet)
            prose_item.setToolTip(prose)
            self.similar_controls_table.setItem(i, 2, prose_item)
            score = entry.get("score", 0.0)
            score_item = QTableWidgetItem(f"{score:.3f}")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.similar_controls_table.setItem(i, 3, score_item)
            self.similar_controls_table.setItem(i, 4, QTableWidgetItem(entry.get("category", "")))
            # Column for mapping status
            mapped = entry.get("has_confirmed_mapping", False)
            map_item = QTableWidgetItem("✅ Yes" if mapped else " No") # No red cross
            map_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if mapped: # Maybe highlight already mapped ones differently?
                 pass # e.g. set background color
            self.similar_controls_table.setItem(i, 5, map_item)

        self.similar_controls_table.resizeColumnsToContents()
        self.similar_controls_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch) # Prose


    def on_fetch_similar_error(self, error_msg: str):
        """ Handles errors when fetching similar controls. """
        self.append_status(f"❌ {error_msg}")
        QMessageBox.critical(self, "Error during context retrieval", error_msg)

    def on_target_selection_changed(self):
        """ Called when a row in the table of similar controls is selected. """
        selected_rows = self.similar_controls_table.selectionModel().selectedRows()
        if selected_rows:
            selected_row_index = selected_rows[0].row()
            item_with_data = self.similar_controls_table.item(selected_row_index, 0)
            if item_with_data:
                 self.selected_target_control_data = item_with_data.data(Qt.ItemDataRole.UserRole)
                 # Activate LLM comparison button if not already mapped?
                 is_already_mapped = self.selected_target_control_data.get("has_confirmed_mapping", False)
                 self.compare_button.setEnabled(not is_already_mapped)
                 # Reset LLM Output and Save button
                 self.llm_output_display.clear()
                 self.save_mapping_button.setEnabled(False)
                 self.current_llm_result = None
                 return # Early exit

        # If no valid row is selected or data is missing
        self.selected_target_control_data = None
        self.compare_button.setEnabled(False)
        self.save_mapping_button.setEnabled(False)
        self.llm_output_display.clear()
        self.current_llm_result = None

    def request_llm_comparison(self):
        """ Starts the LLM comparison for the selected pair. """
        if not self.locked_control_data or not self.selected_target_control_data:
             QMessageBox.warning(self, "Selection Missing", "Source and a similar target must be selected.")
             return

        source_prose = self.locked_control_data.get('prose')
        target_prose = self.selected_target_control_data.get('target_prose')
        target_id = self.selected_target_control_data.get('target_id')

        if not source_prose or not target_prose:
             QMessageBox.critical(self, "Error", "Prose text for source or target is missing.")
             return

        self.append_status(f"Starting LLM comparison for {self.locked_control_data['control_id']} <-> {target_id}...")
        self.compare_button.setEnabled(False)
        self.save_mapping_button.setEnabled(False)
        self.llm_output_display.clear()
        self.current_llm_result = None

        # Start LLM Task
        task = LLMComparisonTask(source_prose, target_prose)
        task.signals.progress.connect(self.append_status)
        task.signals.finished.connect(self.display_llm_result)
        task.signals.error.connect(self.handle_llm_error)
        self.threadpool.start(task)


    def display_llm_result(self, result_tuple: Tuple[Optional[str], str]):
        """ Displays the result of the LLM comparison. """
        classification, explanation = result_tuple
        self.append_status("LLM response received.")
        display_text = f"LLM Classification: {classification or 'Unknown/Error'}\n\nExplanation:\n{explanation}"
        self.llm_output_display.setPlainText(display_text)
        # Store the result for the Save button
        self.current_llm_result = {"type": classification, "explanation": explanation}
        # Activate buttons
        # Compare button remains deactivated until a new selection is made
        # Activate Save button if classification was valid?
        self.save_mapping_button.setEnabled(classification is not None)


    def handle_llm_error(self, error_msg: str):
         """ Handles errors from the LLM task. """
         self.append_status(f"❌ {error_msg}")
         self.llm_output_display.setPlainText(f"Error during LLM analysis:\n{error_msg}")
         QMessageBox.critical(self, "LLM Error", error_msg)
         # Re-activate buttons (only Compare, as saving is not possible)
         is_already_mapped = self.selected_target_control_data.get("has_confirmed_mapping", False) if self.selected_target_control_data else True
         self.compare_button.setEnabled(not is_already_mapped)
         self.save_mapping_button.setEnabled(False)


    def save_mapping(self):
        """ Saves the currently displayed LLM mapping in Neo4j. """
        if not self.locked_control_data or not self.selected_target_control_data or not self.current_llm_result:
            QMessageBox.warning(self, "Error", "No valid LLM result selected for saving.")
            return

        source_id = self.locked_control_data['control_id']
        target_id = self.selected_target_control_data['target_id']
        llm_type = self.current_llm_result.get('type')
        llm_explanation = self.current_llm_result.get('explanation')

        if not llm_type: # Only save if classification was successful
             QMessageBox.warning(self, "Invalid Result", "LLM result has no valid classification for saving.")
             return

        # Get the original similarity score for the properties
        original_similarity = self.selected_target_control_data.get('score', 0.0)

        # TODO: Fetch missing properties from UI or fixed values if necessary (provenance, confidence, status)
        properties_to_save = {
             "type": llm_type,
             "explanation": llm_explanation,
             "similarity": original_similarity, # Original score as reference
             "method": "LLM", # Assumption: Always LLM here
             "provenance": "C-FUSE RAG Mapping", # Example
             "confidence": None, # TODO: Does LLM provide this?
             "status": "pending_validation" # LLM recommendation -> waiting for validation by human
        }
        # Remove None values, if desired
        properties_to_save = {k:v for k,v in properties_to_save.items() if v is not None}


        self.append_status(f"Saving mapping {source_id} -> {target_id}...")
        self.save_mapping_button.setEnabled(False) # Deactivate while saving

        # TODO: Possibly move saving to a worker as well? Synchronous for now.
        try:
            success = save_confirmed_mapping(source_id, target_id, properties_to_save)
            if success:
                 self.append_status("✅ Mapping saved successfully.")
                 QMessageBox.information(self, "Saved", "Mapping was saved successfully.")
                 # Update the display in the "Similar Controls" table
                 self.fetch_and_display_similar_controls() # Reloads and shows mapping status
                 # Deactivate Compare button for this pair after saving
                 self.compare_button.setEnabled(False)
            else:
                 # Should be caught by exception
                 self.append_status("❌ Saving failed (DB function returned False).")
                 QMessageBox.warning(self, "Error", "Mapping could not be saved (DB error).")
                 self.save_mapping_button.setEnabled(True) # Allow saving again?

        except Exception as e:
            self.append_status(f"❌ Error saving the mapping: {e}")
            log.error("Error in save_mapping slot:", exc_info=True)
            QMessageBox.critical(self, "Save Error", f"Error during saving:\n{e}")
            self.save_mapping_button.setEnabled(True) # Allow saving again on error


    def reload_catalog_data(self):
        # (Code as in ControlMappingView)
        self.append_status("Reloading catalog data...")
        try:
            # Ensure signals are blocked only around clear/addItems if needed,
            # or ensure update_source_group_selector handles its own signals correctly
            # self.source_catalog_selector.blockSignals(True) # Careful with blocking/unblocking
            self.populate_catalog_selectors()
        finally:
            # self.source_catalog_selector.blockSignals(False) # Ensure unblocked
            # populate_catalog_selectors should call update_source_group_selector if data changed
            pass # Handled in populate_catalog_selectors by triggering update
        self.append_status("🔄 Catalog list updated.")

    def closeEvent(self, event):
         # (Code as in ControlMappingView)
         log.debug("RAGMappingView is closing.")
         # Consider stopping QThreadPool tasks if they are long-running and it's safe to do so.
         # self.threadpool.clear() # This would remove queued tasks
         # self.threadpool.waitForDone(-1) # This would wait for active tasks
         super().closeEvent(event)