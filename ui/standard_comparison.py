# ui/standard_comparison.py

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QComboBox, QPushButton,
    QTextBrowser, QHBoxLayout, QMessageBox
)
from logic.DSPy_version import run_comparison, init_dspy
from assets.markdown_utils import beautify_markdown

class CybersecurityComparer(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(900)
        init_dspy()

        self.standards = [
            "ISO27001:2022", "ISO27001:2013", "NIST CSF", "BSI IT-Grundschutz", "COBIT", "PCI DSS", "TISAX",
            "HIPAA", "GDPR", "SOC 2", "FedRAMP", "ANSSI RGS", "Cyber Essentials", "ASVS", "NERC CIP", "CMMC",
            "ISO22301", "ISO31000", "C5", "COSO ERM", "ISA/IEC 62443", "NIS Directive", # Translated from "NIS-Richtlinie"
            "ISO27002", "CIS Controls", "ISO27701", "CCPA", "IEC 62304", "ISO13485", "FISMA", "ISO29100", "PIPEDA"
        ]

        self.standard_a = QComboBox()
        self.standard_a.addItems(self.standards)

        self.standard_b = QComboBox()
        self.standard_b.addItems(self.standards)
        self.standard_b.setCurrentIndex(1)

        self.compare_button = QPushButton("Start Comparison")
        self.compare_button.clicked.connect(self.perform_comparison)

        self.result_area = QTextBrowser()
        self.result_area.setOpenExternalLinks(True)

        layout = QVBoxLayout()

        def labeled_widget(label_text, widget):
            box = QVBoxLayout()
            label = QLabel(label_text)
            box.addWidget(label)
            box.addWidget(widget)
            return box

        hbox1 = QHBoxLayout()
        hbox1.addLayout(labeled_widget("Standard A:", self.standard_a))
        hbox1.addSpacing(20)
        hbox1.addLayout(labeled_widget("Standard B:", self.standard_b))

        layout.addLayout(hbox1)
        layout.addWidget(self.compare_button)
        layout.addWidget(QLabel("Comparison Result:"))
        layout.addWidget(self.result_area)

        self.setLayout(layout)

    def perform_comparison(self):
        a = self.standard_a.currentText()
        b = self.standard_b.currentText()

        self.result_area.setHtml("<i>Running comparison... Please wait.</i>")
        try:
            result = run_comparison(a, b)
            formatted = beautify_markdown(result)
            self.result_area.setHtml(formatted)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred:\n{str(e)}")
            self.result_area.clear()