# Filename: ui/human_validation_view.py

import logging
from typing import List, Dict, Any, Optional

from PySide6.QtCore import Qt, QThreadPool, QRunnable, QObject, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QTextEdit, QMessageBox, QSplitter, QDialog, QInputDialog
)

from db.hitl_queries import (
    get_mappings_for_validation,
    delete_mapping_relationship,
    get_mapping_detail,
)
from logic.hitl_processes import (
    human_validate_without_changes,
    human_edit_and_confirm,
)
from db.queries_embeddings import get_all_catalogs

log = logging.getLogger(__name__)

VALID_TYPES = ["EQUAL", "SUBSET", "SUPERSET", "RELATED", "UNRELATED", "ERROR"]
STATUS_FILTERS = ["pending_validation", "human_validated", "confirmed", "rejected"]


# ---------- Worker Infra ----------

class WorkerSignals(QObject):
    finished = Signal(object)   # payload
    error = Signal(str)
    progress = Signal(str)


class FuncTask(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as e:
            log.exception("Background task failed")
            self.signals.error.emit(str(e))


# ---------- Manage-Dialog (Save / Validate / Reject / Delete) ----------

class EditMappingDialog(QDialog):
    """
    Popup zum Bearbeiten (type/explanation) und Aktionen:
      - Save     -> Human/confirmed (mit Archivierung in hitl_processes)
      - Validate -> LLM/human_validated (keine inhaltliche Änderung)
      - Reject   -> Human/rejected (optional Reason)
      - Delete   -> Beziehung löschen (doppelte Bestätigung bereits hier)
      - Cancel
    """
    def __init__(self, parent, current_type: str, current_expl: str,
                 src_id: str, tgt_id: str):
        super().__init__(parent)
        self.setWindowTitle(f"Manage mapping: {src_id} → {tgt_id}")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.type_combo = QComboBox()
        for t in VALID_TYPES:
            self.type_combo.addItem(t, t)
        idx = self.type_combo.findData((current_type or "").upper())
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.expl_edit = QTextEdit()
        self.expl_edit.setPlainText(current_expl or "")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_save = QPushButton("Save")
        self.btn_validate = QPushButton("Validate")
        self.btn_reject = QPushButton("Reject")
        self.btn_delete = QPushButton("Delete")
        btn_cancel = QPushButton("Cancel")

        self.btn_save.clicked.connect(self._on_save_clicked)
        self.btn_validate.clicked.connect(self._on_validate_clicked)
        self.btn_reject.clicked.connect(self._on_reject_clicked)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        btn_cancel.clicked.connect(self.reject)

        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_save)
        btn_row.addWidget(self.btn_validate)
        btn_row.addWidget(self.btn_reject)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(btn_cancel)

        layout.addWidget(QLabel("Type:"))
        layout.addWidget(self.type_combo)
        layout.addWidget(QLabel("Explanation:"))
        layout.addWidget(self.expl_edit, 1)
        layout.addLayout(btn_row)

        self._action: Optional[str] = None      # "save"|"validate"|"reject"|"delete"|None
        self._values: Optional[tuple] = None    # (type, explanation)
        self._reject_reason: Optional[str] = None
        self._src_id, self._tgt_id = src_id, tgt_id

    def action(self) -> Optional[str]:
        return self._action

    def values(self) -> Optional[tuple]:
        return self._values

    def reject_reason(self) -> Optional[str]:
        return self._reject_reason

    def _on_save_clicked(self):
        self._action = "save"
        self._values = (self.type_combo.currentData(), self.expl_edit.toPlainText().strip())
        self.accept()

    def _on_validate_clicked(self):
        self._action = "validate"
        self.accept()

    def _on_reject_clicked(self):
        reason, ok = QInputDialog.getText(self, "Rejection reason (optional)", "Note to store on relationship:")
        if not ok:
            return
        self._reject_reason = reason or None
        self._action = "reject"
        self.accept()

    def _on_delete_clicked(self):
        if QMessageBox.question(self, "Delete Mapping",
                                f"Mapping {self._src_id} → {self._tgt_id} wirklich löschen?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        msg = ("Das Mapping wurde vom System/LLM vorgeschlagen und/oder manuell bearbeitet.\n"
               "Durch Löschen gehen diese Informationen verloren.\n\nWirklich fortfahren?")
        if QMessageBox.question(self, "Confirm Delete", msg,
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._action = "delete"
        self.accept()


# ---------- View ----------

class HumanValidationView(QWidget):
    """
    UI zum Prüfen/Bearbeiten/Löschen bestehender :IS_MAPPED_TO-Mappings.
    - Table: nur ein 'Manage'-Button pro Zeile (öffnet Popup)
    - Score/Prose/IDs read-only
    """
    def __init__(self):
        super().__init__()
        self.setObjectName("HumanValidationView")
        self.threadpool = QThreadPool.globalInstance()

        self.rows_data: List[Dict[str, Any]] = []
        self.selected_row: Optional[int] = None

        # --- Filterleiste ---
        self.src_catalog = QComboBox()
        self.tgt_catalog = QComboBox()
        self.status_filter = QComboBox()
        self.reload_btn = QPushButton("Reload")

        self._populate_catalogs()

        self.status_filter.addItem("<All>", None)
        for s in STATUS_FILTERS:
            self.status_filter.addItem(s, s)

        # --- Tabelle ---
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Source ID", "Target ID", "Type", "Explanation", "Score",
            "Status", "Method", "Actions"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setMinimumSectionSize(110)

        # Zeilenabstand / Lesbarkeit
        self.table.setStyleSheet("QTableWidget::item{ padding:6px 8px; }")
        self.table.itemSelectionChanged.connect(self._on_row_selected)

        # --- Detailbereich (read-only Texte) ---
        self.source_prose = QTextEdit(); self.source_prose.setReadOnly(True)
        self.target_prose = QTextEdit(); self.target_prose.setReadOnly(True)

        # --- Layout ---
        top = QHBoxLayout()
        top.setSpacing(12)
        top.setContentsMargins(6, 6, 6, 6)
        top.addWidget(QLabel("Source Catalog:"))
        top.addWidget(self.src_catalog, 1)
        top.addSpacing(8)
        top.addWidget(QLabel("Target Catalog:"))
        top.addWidget(self.tgt_catalog, 1)
        top.addSpacing(8)
        top.addWidget(QLabel("Status:"))
        top.addWidget(self.status_filter)
        top.addSpacing(8)
        top.addWidget(self.reload_btn)

        details_split = QSplitter(Qt.Orientation.Horizontal)
        left_box = QVBoxLayout()
        left_widget = QWidget(); left_widget.setLayout(left_box)
        left_box.setSpacing(8)
        left_box.setContentsMargins(6, 6, 6, 6)
        left_box.addWidget(QLabel("Mappings (Manage via popup):"))
        left_box.addWidget(self.table)

        right_box = QVBoxLayout()
        right_widget = QWidget(); right_widget.setLayout(right_box)
        right_box.setSpacing(8)
        right_box.setContentsMargins(6, 6, 6, 6)
        right_box.addWidget(QLabel("Source Control (read-only):"))
        right_box.addWidget(self.source_prose, 1)
        right_box.addWidget(QLabel("Target Control (read-only):"))
        right_box.addWidget(self.target_prose, 1)

        details_split.addWidget(left_widget)
        details_split.addWidget(right_widget)
        details_split.setSizes([700, 400])

        main = QVBoxLayout(self)
        main.setSpacing(8)
        main.setContentsMargins(6, 6, 6, 6)
        main.addLayout(top)
        main.addWidget(details_split, 1)

        # --- Signals ---
        self.reload_btn.clicked.connect(self.reload_data)

        # Start
        self.reload_data()

    # ---------- Data loading ----------

    def _populate_catalogs(self):
        self.src_catalog.clear(); self.tgt_catalog.clear()
        self.src_catalog.addItem("<Any>", None)
        self.tgt_catalog.addItem("<Any>", None)
        try:
            for c in get_all_catalogs():
                self.src_catalog.addItem(c["title"], c["uuid"])
                self.tgt_catalog.addItem(c["title"], c["uuid"])
        except Exception:
            log.exception("Error loading catalogs")
            QMessageBox.critical(self, "Error", "Could not load catalogs for filters.")

    def reload_data(self):
        src = self.src_catalog.currentData()
        tgt = self.tgt_catalog.currentData()
        status = self.status_filter.currentData()
        params = {
            "source_catalog_uuid": src,
            "target_catalog_uuid": tgt,
            "status_filter": [status] if status else None,
            "limit": 200
        }
        task = FuncTask(get_mappings_for_validation, **params)
        task.signals.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        task.signals.finished.connect(self._populate_table)
        self.threadpool.start(task)

    def _populate_table(self, rows: List[Dict[str, Any]]):
        self.rows_data = rows or []
        self.table.setRowCount(len(self.rows_data))
        self.source_prose.clear(); self.target_prose.clear()

        for r, row in enumerate(self.rows_data):
            # Zeilenhöhe + später Button-Höhe
            row_h = 40
            self.table.setRowHeight(r, row_h)

            # IDs
            it_src = QTableWidgetItem(row.get("source_id","")); it_src.setData(Qt.ItemDataRole.UserRole, row)
            it_tgt = QTableWidgetItem(row.get("target_id",""))
            self.table.setItem(r, 0, it_src)
            self.table.setItem(r, 1, it_tgt)

            # Type (Text)
            type_txt = (row.get("type") or "").upper()
            self.table.setItem(r, 2, QTableWidgetItem(type_txt))

            # Explanation (Text + Tooltip)
            expl = row.get("explanation","") or ""
            expl_item = QTableWidgetItem(expl)
            expl_item.setToolTip(expl)
            self.table.setItem(r, 3, expl_item)

            # Score
            sc = row.get("similarity", 0.0)
            it_sc = QTableWidgetItem(f"{sc:.3f}")
            it_sc.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 4, it_sc)

            # Status / Method
            self.table.setItem(r, 5, QTableWidgetItem(row.get("status","") or ""))
            self.table.setItem(r, 6, QTableWidgetItem(row.get("method","") or ""))

            # Actions: EIN Button "Manage"
            manage_btn = QPushButton("Manage")
            manage_btn.setMinimumHeight(max(28, row_h - 8))
            manage_btn.clicked.connect(lambda _=False, i=r: self._on_manage_clicked(i))
            self.table.setCellWidget(r, 7, manage_btn)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(False)

    # ---------- Row selection & details ----------

    def _on_row_selected(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            self.selected_row = None
            self.source_prose.clear(); self.target_prose.clear()
            return
        self.selected_row = sel[0].row()
        row = self.rows_data[self.selected_row]
        self.source_prose.setPlainText(row.get("source_prose","") or "")
        self.target_prose.setPlainText(row.get("target_prose","") or "")

    # ---------- Manage Popup ----------

    def _on_manage_clicked(self, row_idx: int):
        row = self.rows_data[row_idx]
        src, tgt = row["source_id"], row["target_id"]
        current_type = (row.get("type") or "").upper()
        current_expl = row.get("explanation") or ""

        dlg = EditMappingDialog(self, current_type, current_expl, src, tgt)
        if dlg.exec() != QDialog.Accepted:
            return

        act = dlg.action()

        # VALIDATE (ohne Änderung)
        if act == "validate":
            task = FuncTask(human_validate_without_changes, src, tgt)
            task.signals.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
            task.signals.finished.connect(lambda ok: self._after_action(ok, row_idx, status="human_validated", method="LLM"))
            self.threadpool.start(task)
            return

        # REJECT
        if act == "reject":
            reason = dlg.reject_reason()
            def do_reject():
                from db.queries_rag import add_mapping_relationship
                props = {"method": "Human", "status": "rejected"}
                if reason:
                    props["annotation"] = str(reason)
                return add_mapping_relationship(src, tgt, props)
            task = FuncTask(do_reject)
            task.signals.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
            task.signals.finished.connect(lambda ok: self._after_action(ok, row_idx, status="rejected", method="Human"))
            self.threadpool.start(task)
            return

        # DELETE
        if act == "delete":
            task = FuncTask(delete_mapping_relationship, src, tgt)
            def done(ok):
                if ok:
                    QMessageBox.information(self, "Deleted", "Mapping gelöscht.")
                    self.reload_data()
                else:
                    QMessageBox.warning(self, "Delete failed", "Löschen fehlgeschlagen.")
            task.signals.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
            task.signals.finished.connect(done)
            self.threadpool.start(task)
            return

        # SAVE (editiert)
        if act == "save":
            new_type, new_expl = dlg.values() or ("", "")
            def do_save():
                current = get_mapping_detail(src, tgt)
                changed = (new_type != (current.get("type") or "")) or (new_expl != (current.get("explanation") or ""))
                if not changed:
                    return "NO_CHANGE"
                ok = human_edit_and_confirm(src, tgt, new_type, new_expl)
                return "SAVED" if ok else "ERROR"

            task = FuncTask(do_save)
            def on_finished(flag):
                if flag == "SAVED":
                    self._after_action(True, row_idx, status="confirmed", method="Human",
                                       new_type=(new_type or "").upper(), new_expl=new_expl)
                elif flag == "NO_CHANGE":
                    if QMessageBox.question(self, "No changes detected",
                                            "Keine Änderungen erkannt. Stattdessen als 'human_validated' bestätigen?",
                                            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                        vt = FuncTask(human_validate_without_changes, src, tgt)
                        vt.signals.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
                        vt.signals.finished.connect(lambda ok: self._after_action(ok, row_idx, status="human_validated", method="LLM"))
                        self.threadpool.start(vt)
                else:
                    QMessageBox.warning(self, "Save failed", "Speichern fehlgeschlagen.")
            task.signals.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
            task.signals.finished.connect(on_finished)
            self.threadpool.start(task)

    # ---------- After action ----------

    def _after_action(self, ok: bool, row_idx: int, status: Optional[str] = None,
                      method: Optional[str] = None, new_type: Optional[str] = None,
                      new_expl: Optional[str] = None):
        if not ok:
            QMessageBox.warning(self, "Operation failed", "Aktion fehlgeschlagen.")
            return
        if status is not None:
            self.table.setItem(row_idx, 5, QTableWidgetItem(status))
            self.rows_data[row_idx]["status"] = status
        if method is not None:
            self.table.setItem(row_idx, 6, QTableWidgetItem(method))
            self.rows_data[row_idx]["method"] = method
        if new_type is not None:
            self.table.setItem(row_idx, 2, QTableWidgetItem((new_type or "").upper()))
            self.rows_data[row_idx]["type"] = (new_type or "").upper()
        if new_expl is not None:
            self.table.setItem(row_idx, 3, QTableWidgetItem(new_expl))
            self.rows_data[row_idx]["explanation"] = new_expl
        QMessageBox.information(self, "Success", "Änderung gespeichert.")