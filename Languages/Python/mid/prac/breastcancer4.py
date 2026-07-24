import sys
from typing import List

from PyQt6.QtCore import Qt, QEasingCurve, QPropertyAnimation, pyqtSlot
from PyQt6.QtGui import QFont, QIcon, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFormLayout, QSpinBox,
    QDoubleSpinBox, QCheckBox, QComboBox, QFrame, QTextEdit,
    QFileDialog, QMessageBox, QGraphicsDropShadowEffect, QScrollArea
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# ---------- Utility: Pretty Card ----------

def make_card_widget() -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    card.setFrameShape(QFrame.Shape.NoFrame)
    card.setStyleSheet("""
        QFrame#card {
            background-color: rgba(255, 255, 255, 230);
            border-radius: 18px;
        }
        QFrame#card QLabel {
            color: #374151;
            font-size: 12px;
        }
    """)
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(24)
    shadow.setXOffset(0)
    shadow.setYOffset(8)
    shadow.setColor(QColor(180, 180, 200, 180))
    card.setGraphicsEffect(shadow)
    return card


# ---------- Matplotlib Canvas ----------

class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=4, height=3, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)


# ---------- Animated Stacked Widget ----------

class AnimatedStackedWidget(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def slide_to_index(self, index: int):
        if index == self.currentIndex():
            return
        old_geom = self.geometry()
        self.setCurrentIndex(index)
        self.setGeometry(old_geom.adjusted(self.width(), 0, self.width(), 0))
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(old_geom)
        self._anim.start()


# ---------- Pages ----------

class HomePage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        card = make_card_widget()
        c_layout = QVBoxLayout(card)

        title = QLabel("Breast Cancer Prediction & Prevention (Educational)")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet("color: #111827;")

        subtitle = QLabel(
            "A pastel-themed AI lab to explore diagnosis demos, multimodal risk, prognosis, "
            "federated learning, explainable AI, and prevention.\n\n"
            "⚠️ This app is a learning tool only. It does NOT provide medical advice, "
            "diagnosis, or treatment recommendations."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #4B5563; font-size: 13px;")

        dense_label = QLabel(
            "<b>Dense Breast Tissue:</b> Dense tissue looks white on a mammogram, "
            "just like many tumors. This makes early detection harder — like looking "
            "for a small white ball in a pile of snow. That’s why doctors may suggest "
            "ultrasound or MRI in addition to mammograms for people with dense breasts."
        )
        dense_label.setWordWrap(True)
        dense_label.setStyleSheet("color: #374151; font-size: 13px;")

        c_layout.addWidget(title)
        c_layout.addSpacing(8)
        c_layout.addWidget(subtitle)
        c_layout.addSpacing(12)
        c_layout.addWidget(dense_label)

        layout.addWidget(card)
        layout.addStretch()


class RiskPage(QWidget):
    """
    Clinical risk + SHAP-like bar chart (fully offline)
    """
    def __init__(self):
        super().__init__()
        self.result = None
        self.shap_contrib = None

        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(16)

        # Left: Form
        left_card = make_card_widget()
        left_layout = QVBoxLayout(left_card)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        label_style = "font-size: 12px; color:#111827;"

        def make_label(text):
            lab = QLabel(text)
            lab.setStyleSheet(label_style)
            return lab

        self.age = QSpinBox()
        self.age.setRange(18, 100)
        self.age.setValue(35)

        self.bmi = QDoubleSpinBox()
        self.bmi.setRange(10, 60)
        self.bmi.setValue(26)
        self.bmi.setDecimals(1)

        self.alcohol = QDoubleSpinBox()
        self.alcohol.setRange(0, 40)
        self.alcohol.setValue(2)
        self.alcohol.setDecimals(1)

        self.activity = QDoubleSpinBox()
        self.activity.setRange(0, 30)
        self.activity.setValue(2)
        self.activity.setDecimals(1)

        self.family = QCheckBox("Yes")
        self.smoking = QCheckBox("Yes")
        self.dense = QCheckBox("Yes")

        form.addRow(make_label("Age (years)"), self.age)
        form.addRow(make_label("BMI"), self.bmi)
        form.addRow(make_label("Alcohol (drinks / week)"), self.alcohol)
        form.addRow(make_label("Physical activity (hrs / week)"), self.activity)
        form.addRow(make_label("Family history of breast cancer"), self.family)
        form.addRow(make_label("Smoking"), self.smoking)
        form.addRow(make_label("Dense breasts"), self.dense)

        header = QLabel("<b>Clinical & Lifestyle Factors</b>")
        header.setStyleSheet("color:#111827; font-size:13px;")

        self.run_btn = QPushButton("Compute Educational Risk")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.clicked.connect(self.run_risk)

        left_layout.addWidget(header)
        left_layout.addLayout(form)
        left_layout.addSpacing(8)
        left_layout.addWidget(self.run_btn)

        self.flags_label = QLabel("")
        self.flags_label.setWordWrap(True)
        self.flags_label.setStyleSheet("color: #374151; font-size: 12px;")
        left_layout.addWidget(self.flags_label)

        main_layout.addWidget(left_card, 1)

        # Right: charts
        right_card = make_card_widget()
        right_layout = QVBoxLayout(right_card)

        self.risk_chart = MplCanvas(self, width=4, height=2)
        self.shap_chart = MplCanvas(self, width=4, height=2)

        caption = QLabel(
            "Top: overall clinical risk score (0–1).\n"
            "Bottom: SHAP-style contributions (demo only) — positive values push risk up, "
            "negative values push risk down."
        )
        caption.setWordWrap(True)
        caption.setStyleSheet("color:#4B5563; font-size:12px;")

        right_header = QLabel("<b>Risk & Explainability</b>")
        right_header.setStyleSheet("color:#111827; font-size:13px;")

        right_layout.addWidget(right_header)
        right_layout.addWidget(self.risk_chart)
        right_layout.addWidget(self.shap_chart)
        right_layout.addWidget(caption)

        main_layout.addWidget(right_card, 1)

    # ---- simple offline "model" ----

    def _compute_risk_and_shap(self):
        age = self.age.value()
        bmi = self.bmi.value()
        alcohol = self.alcohol.value()
        activity = self.activity.value()
        family = self.family.isChecked()
        smoking = self.smoking.isChecked()
        dense = self.dense.isChecked()

        # Base risk and contributions for each feature
        base = 0.05
        contrib = {}

        # Age
        if age <= 30:
            c_age = -0.01
        elif age <= 40:
            c_age = 0.03
        elif age <= 50:
            c_age = 0.06
        else:
            c_age = 0.10
        contrib["Age"] = c_age

        # BMI
        if bmi < 22:
            c_bmi = -0.02
        elif bmi < 27:
            c_bmi = 0.00
        elif bmi < 32:
            c_bmi = 0.04
        else:
            c_bmi = 0.08
        contrib["BMI"] = c_bmi

        # Alcohol
        if alcohol == 0:
            c_alcohol = -0.01
        elif alcohol < 5:
            c_alcohol = 0.02
        elif alcohol < 15:
            c_alcohol = 0.05
        else:
            c_alcohol = 0.10
        contrib["Alcohol"] = c_alcohol

        # Activity
        if activity >= 7:
            c_act = -0.06
        elif activity >= 3:
            c_act = -0.03
        elif activity > 0:
            c_act = -0.01
        else:
            c_act = 0.02
        contrib["Activity"] = c_act

        # Smoking
        contrib["Smoking"] = 0.08 if smoking else -0.02

        # Family history
        contrib["Family history"] = 0.10 if family else -0.01

        # Dense breasts
        contrib["Dense breasts"] = 0.05 if dense else 0.0

        score = base + sum(contrib.values())
        score = max(0.01, min(0.95, score))

        # Flags / messages
        flags = []
        if family:
            flags.append("Family history present")
        if bmi >= 27:
            flags.append("Elevated BMI")
        if smoking:
            flags.append("Smoking")
        if alcohol >= 7:
            flags.append("High alcohol intake")
        if activity < 3:
            flags.append("Low physical activity")
        if dense:
            flags.append("Dense breast tissue (screening may be harder)")

        return score, contrib, flags

    @pyqtSlot()
    def run_risk(self):
        score, contrib, flags = self._compute_risk_and_shap()
        self.result = {
            "clinical_risk_score": score,
            "lifestyle_flags": flags,
        }
        self.shap_contrib = contrib
        self.update_ui()

    def update_ui(self):
        if not self.result:
            return

        score = self.result["clinical_risk_score"]
        flags = self.result.get("lifestyle_flags", [])
        self.flags_label.setText(
            f"Clinical risk score (demo): <b>{score:.2f}</b><br>"
            f"Lifestyle flags: {', '.join(flags) if flags else 'None'}"
        )

        # Risk chart (single bar)
        ax = self.risk_chart.axes
        ax.clear()
        ax.bar(["Clinical"], [score])
        ax.set_ylim(0, 1)
        ax.set_ylabel("Risk (0–1)")
        self.risk_chart.draw()

        # SHAP-like chart
        if self.shap_contrib:
            features = list(self.shap_contrib.keys())
            values = list(self.shap_contrib.values())
            ax2 = self.shap_chart.axes
            ax2.clear()
            ax2.barh(features, values)
            ax2.axvline(0, linewidth=0.8)
            ax2.set_xlabel("Contribution to risk (demo)")
            self.shap_chart.draw()


class DiagnosisPage(QWidget):
    """
    Image upload + *fake* diagnosis demo (no real model)
    """
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setSpacing(16)

        left = make_card_widget()
        l_layout = QVBoxLayout(left)
        l_layout.addWidget(QLabel("<b>AI Diagnosis Demo (Image)</b>"))

        self.path_label = QLabel("No file selected")
        self.path_label.setStyleSheet("color:#4B5563; font-size: 12px;")
        self.dense_box = QCheckBox("Simulate dense breasts")

        self.select_btn = QPushButton("Choose Image...")
        self.select_btn.clicked.connect(self.select_image)

        self.run_btn = QPushButton("Run AI Demo (Offline Mock)")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.clicked.connect(self.run_diagnosis)

        l_layout.addWidget(self.path_label)
        l_layout.addWidget(self.dense_box)
        l_layout.addSpacing(8)
        l_layout.addWidget(self.select_btn)
        l_layout.addWidget(self.run_btn)
        l_layout.addStretch()

        layout.addWidget(left, 1)

        right = make_card_widget()
        r_layout = QVBoxLayout(right)

        self.result_label = QLabel(
            "Upload a mammogram / ultrasound image to see a <i>simulated</i> suspicion score "
            "and a text explanation.\n\n"
            "No real medical analysis is performed."
        )
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("color:#4B5563; font-size:12px;")

        r_layout.addWidget(QLabel("<b>Result & Explanation</b>"))
        r_layout.addWidget(self.result_label)
        r_layout.addStretch()

        layout.addWidget(right, 1)

        self.image_path = None

    @pyqtSlot()
    def select_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Mammogram/Ultrasound", "",
            "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self.image_path = path
            self.path_label.setText(path)

    @pyqtSlot()
    def run_diagnosis(self):
        if not self.image_path:
            QMessageBox.information(self, "No image", "Please select an image first.")
            return

        # Completely fake scoring: just alternate between low / medium / high
        dense = self.dense_box.isChecked()
        hash_val = hash(self.image_path) % 100
        if hash_val < 30:
            score = 0.18
            label = "Likely benign (demo)"
            explanation = (
                "Most of the texture appears smooth, with well-defined borders. "
                "In this offline demo, that pattern is given a low suspicion score."
            )
        elif hash_val < 70:
            score = 0.45
            label = "Indeterminate (demo)"
            explanation = (
                "There are some areas of asymmetry and mixed density. "
                "In a real workflow, this would typically require additional views "
                "or another imaging modality."
            )
        else:
            score = 0.78
            label = "Suspicious (demo)"
            explanation = (
                "The simulated model focuses on a tighter, irregular region with "
                "spiculated margins, which in practice can be associated with "
                "higher concern — again, this is purely illustrative."
            )

        dense_warning = ""
        if dense:
            score = min(0.95, score + 0.08)
            dense_warning = (
                "Dense tissue can mask cancers and also produces more bright areas, "
                "so even a low or medium score would never be enough to ignore "
                "clinical symptoms."
            )

        text = (
            f"Suspicion score (offline demo): <b>{score:.2f}</b><br>"
            f"Label: <b>{label}</b><br><br>"
            f"{explanation}<br><br>"
        )
        if dense_warning:
            text += f"<span style='color:#b45309;'>⚠ {dense_warning}</span><br><br>"
        text += (
            "<i>In a real Grad-CAM explanation, a heatmap would highlight the regions "
            "that contributed most to this score. Here we only show text.</i>"
        )

        self.result_label.setText(text)


class PrognosisPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setSpacing(16)

        left = make_card_widget()
        l = QVBoxLayout(left)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        def lab(text):
            q = QLabel(text)
            q.setStyleSheet("color:#111827; font-size:12px;")
            return q

        self.tumor_size = QDoubleSpinBox()
        self.tumor_size.setRange(0, 200)
        self.tumor_size.setValue(20)

        self.nodes = QSpinBox()
        self.nodes.setRange(0, 50)
        self.nodes.setValue(0)

        self.stage = QComboBox()
        self.stage.addItems(["I", "II", "III", "IV"])

        self.grade = QComboBox()
        self.grade.addItems(["1", "2", "3"])

        self.er = QCheckBox("ER+")
        self.er.setChecked(True)
        self.pr = QCheckBox("PR+")
        self.pr.setChecked(True)
        self.her2 = QCheckBox("HER2+")
        self.chemo = QCheckBox("Chemotherapy received")
        self.chemo.setChecked(True)
        self.hormone = QCheckBox("Hormone therapy")
        self.hormone.setChecked(True)
        self.surgery = QCheckBox("Surgery done")
        self.surgery.setChecked(True)

        l.addWidget(QLabel("<b>Prognosis Inputs (Demo)</b>"))

        form.addRow(lab("Tumor size (mm)"), self.tumor_size)
        form.addRow(lab("Positive lymph nodes"), self.nodes)
        form.addRow(lab("Stage"), self.stage)
        form.addRow(lab("Grade"), self.grade)
        form.addRow(self.er)
        form.addRow(self.pr)
        form.addRow(self.her2)
        form.addRow(self.chemo)
        form.addRow(self.hormone)
        form.addRow(self.surgery)
        l.addLayout(form)

        self.run_btn = QPushButton("Run Prognosis Demo")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.clicked.connect(self.run_prognosis)
        l.addWidget(self.run_btn)
        l.addStretch()

        layout.addWidget(left, 1)

        right = make_card_widget()
        r = QVBoxLayout(right)
        self.prog_label = QLabel(
            "This curve is a <b>toy</b> recurrence-risk simulator over 10 years. "
            "It is not calibrated to real patient outcomes."
        )
        self.prog_label.setWordWrap(True)
        self.prog_label.setStyleSheet("color:#4B5563; font-size:12px;")

        self.timeline = MplCanvas(self, width=4, height=2)

        r.addWidget(QLabel("<b>Recurrence Curve (Offline Demo)</b>"))
        r.addWidget(self.timeline)
        r.addWidget(self.prog_label)

        layout.addWidget(right, 1)

    def _payload(self):
        return {
            "tumor_size_mm": self.tumor_size.value(),
            "lymph_nodes_positive": self.nodes.value(),
            "stage": self.stage.currentText(),
            "grade": int(self.grade.currentText()),
            "er_status": self.er.isChecked(),
            "pr_status": self.pr.isChecked(),
            "her2_status": self.her2.isChecked(),
            "chemo": self.chemo.isChecked(),
            "hormone_therapy": self.hormone.isChecked(),
            "surgery": self.surgery.isChecked()
        }

    @pyqtSlot()
    def run_prognosis(self):
        p = self._payload()

        # Very rough scoring to shape the curve
        stage_factor = {"I": 0.12, "II": 0.22, "III": 0.4, "IV": 0.6}[p["stage"]]
        size_factor = min(0.3, p["tumor_size_mm"] / 100.0)
        node_factor = min(0.25, p["lymph_nodes_positive"] * 0.02)
        grade_factor = {1: 0.05, 2: 0.12, 3: 0.2}[p["grade"]]

        therapy_bonus = 0.0
        if p["chemo"]:
            therapy_bonus -= 0.08
        if p["hormone_therapy"] and p["er_status"]:
            therapy_bonus -= 0.08
        if p["surgery"]:
            therapy_bonus -= 0.10

        baseline = stage_factor + size_factor + node_factor + grade_factor + therapy_bonus
        baseline = max(0.05, min(0.8, baseline))

        # Build a curve: initially higher risk, then tapering off
        years = list(range(1, 11))
        curve = []
        for y in years:
            year_risk = baseline * (0.4 + 0.8 * (1.0 / (y ** 0.7)))
            curve.append(max(0.01, min(0.95, year_risk)))

        # Risk category for text
        if baseline < 0.18:
            risk_cat = "Lower simulated risk"
        elif baseline < 0.35:
            risk_cat = "Intermediate simulated risk"
        else:
            risk_cat = "Higher simulated risk"

        self.prog_label.setText(
            f"Risk category (demo): <b>{risk_cat}</b>.<br>"
            f"Therapies decrease the overall curve; larger tumors, more nodes, and higher stage/grade push it up."
        )

        ax = self.timeline.axes
        ax.clear()
        ax.plot(years, curve, marker="o")
        ax.set_xlabel("Years from diagnosis")
        ax.set_ylabel("Simulated recurrence risk")
        ax.set_ylim(0, 1)
        self.timeline.draw()


class FederatedPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        card = make_card_widget()
        c = QVBoxLayout(card)

        top_row = QHBoxLayout()
        self.rounds = QSpinBox()
        self.rounds.setRange(1, 50)
        self.rounds.setValue(8)
        self.sites = QSpinBox()
        self.sites.setRange(2, 10)
        self.sites.setValue(3)

        run_btn = QPushButton("Start FL Simulation (Offline)")
        run_btn.setObjectName("primaryButton")
        run_btn.clicked.connect(self.run_fl)

        top_row.addWidget(QLabel("Rounds"))
        top_row.addWidget(self.rounds)
        top_row.addSpacing(12)
        top_row.addWidget(QLabel("Sites"))
        top_row.addWidget(self.sites)
        top_row.addStretch()
        top_row.addWidget(run_btn)

        self.fl_chart = MplCanvas(self, width=5, height=2)
        self.fl_label = QLabel(
            "Simulated global accuracy over federated rounds. "
            "Each site trains locally; the server averages model weights."
        )
        self.fl_label.setWordWrap(True)
        self.fl_label.setStyleSheet("color:#4B5563; font-size:12px;")

        c.addWidget(QLabel("<b>Federated Learning Simulator</b>"))
        c.addLayout(top_row)
        c.addWidget(self.fl_chart)
        c.addWidget(self.fl_label)

        layout.addWidget(card)

    @pyqtSlot()
    def run_fl(self):
        rounds = self.rounds.value()
        sites = self.sites.value()

        # Simple simulated learning curve
        global_acc = []
        acc = 0.55
        for r in range(rounds):
            improvement = 0.03 * (1.0 / (1 + r / 3.0)) * (min(sites, 6) / 6.0)
            acc = min(0.97, acc + improvement)
            global_acc.append(acc)

        ax = self.fl_chart.axes
        ax.clear()
        ax.plot(range(1, rounds + 1), global_acc, marker="o")
        ax.set_xlabel("Round")
        ax.set_ylabel("Global accuracy (demo)")
        ax.set_ylim(0.5, 1.0)
        self.fl_chart.draw()

        self.fl_label.setText(
            f"After {rounds} rounds with {sites} virtual hospitals, "
            f"simulated global accuracy reaches about {global_acc[-1]:.2f}.\n"
            "In real FL, some sites may have more noise or different populations, which affects convergence."
        )


class XaiPage(QWidget):
    """
    Expanded XAI explanation page (offline).
    """
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        card = make_card_widget()
        c = QVBoxLayout(card)

        title = QLabel("<b>Explainable AI (XAI)</b>")
        title.setStyleSheet("font-size:14px; color:#111827;")

        body = QLabel(
            "Explainable AI helps us understand <i>why</i> a model made a prediction, "
            "not just what the prediction was.\n\n"
            "<b>For tabular / clinical data:</b>\n"
            "• Techniques like SHAP assign a contribution value to each feature (age, BMI, smoking, etc.).\n"
            "• Positive values push the predicted risk upward; negative values pull it down.\n"
            "• In the Risk page, the horizontal bars act as a SHAP-style explanation.\n\n"
            "<b>For images:</b>\n"
            "• Grad-CAM and similar methods build a heatmap on top of the image.\n"
            "• Regions that strongly influenced the prediction light up in warm colors.\n"
            "• A good heatmap should highlight clinically meaningful structures (masses, calcifications, distortions) "
            "instead of random noise.\n\n"
            "This page generates a mock image-based explanation that you can read like a report."
        )
        body.setWordWrap(True)
        body.setStyleSheet("color:#4B5563; font-size:12px;")

        self.image_explain = QTextEdit()
        self.image_explain.setReadOnly(True)
        self.image_explain.setStyleSheet(
            "background: transparent; color:#111827; font-size:12px;"
        )

        btn = QPushButton("Generate Mock Image XAI Report")
        btn.setObjectName("primaryButton")
        btn.clicked.connect(self.load_image_xai)

        c.addWidget(title)
        c.addWidget(body)
        c.addSpacing(12)
        c.addWidget(btn)
        c.addWidget(self.image_explain)

        layout.addWidget(card)

    @pyqtSlot()
    def load_image_xai(self):
        # Offline, just generate a consistent text block
        template = (
            "Grad-CAM Summary (offline demo)\n"
            "--------------------------------\n"
            "• The simulated model focuses on a patch in the upper-outer quadrant of the breast.\n"
            "• The heatmap is strongest around a slightly irregular, high-density region.\n"
            "• Surrounding fibroglandular tissue shows moderate activation.\n"
            "• The skin line and chest wall show minimal activation, which is expected.\n\n"
            "How to interpret this in practice:\n"
            "• If the most active regions correspond to a benign structure (e.g., a cyst confirmed on ultrasound), "
            "then a high score might indicate the model is overfitting to the wrong signal.\n"
            "• If activation is centered on the true lesion, it increases trust in the model — "
            "but it still cannot replace a radiologist’s judgement.\n\n"
            "Remember: this report is generated without any real imaging model; "
            "it is only here to help you practice reading XAI-style descriptions."
        )
        self.image_explain.setPlainText(template)


class PreventionPage(QWidget):
    """
    Expanded prevention & awareness content.
    """
    def __init__(self):
        super().__init__()

        outer_layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        card = make_card_widget()
        c = QVBoxLayout(card)

        title = QLabel("<b>Prevention & Awareness</b>")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color:#111827;")

        text = QLabel(
            "These points are based on commonly discussed risk factors and healthy habits. "
            "They are <b>general</b> and not personalized medical advice.\n\n"
            "<b>1. Everyday lifestyle habits</b>\n"
            "• Maintain a healthy weight: excess body fat, especially after menopause, is linked to higher risk.\n"
            "• Move your body regularly: aim for at least 150 minutes of moderate activity per week "
            "(for example, 30 minutes on most days).\n"
            "• Limit alcohol: even small amounts can increase risk; many guidelines suggest keeping it as low as "
            "possible or avoiding alcohol.\n"
            "• Avoid or quit smoking: smoking is harmful for overall health and is associated with several cancers.\n\n"
            "<b>2. Screening & early detection (talk to your doctor)</b>\n"
            "Exact recommendations vary by country and personal risk, but discussions often include:\n"
            "• Clinical breast exams and regular check-ups.\n"
            "• Screening mammograms from a certain age (for many people this is somewhere between 40–50).\n"
            "• Earlier and more frequent screening if there is a strong family history or known genetic mutation.\n"
            "• For dense breasts, doctors may add ultrasound or MRI to improve detection.\n\n"
            "<b>3. Breast self-awareness</b>\n"
            "Instead of a strict 'self-exam schedule', many organisations now talk about being familiar with "
            "how your breasts normally look and feel:\n"
            "• Notice any new lump, thickening, or area that feels different from the rest.\n"
            "• Watch for changes in size, shape, skin dimpling, redness, or nipple inversion.\n"
            "• Pay attention to persistent pain in one spot or unusual nipple discharge.\n"
            "• If something feels off and does not go away, contact a healthcare professional.\n\n"
            "<b>4. Family history & genetics</b>\n"
            "• Having a close relative (parent, sibling, child) with breast or ovarian cancer can increase risk.\n"
            "• Some families carry gene variants (e.g., BRCA1/2) that greatly change risk and screening strategy.\n"
            "• If many relatives are affected, or cancer appeared at young ages, a genetics consultation may help.\n\n"
            "<b>5. Mental health & support</b>\n"
            "• Worry about cancer is very common; it can affect sleep, mood, and concentration.\n"
            "• Talking with friends, family, support groups, or a mental health professional can make a big difference.\n"
            "• No app — including this one — can replace human connection and professional care.\n\n"
            "<b>Important:</b> Any new symptom, worry, or change should be discussed with a qualified clinician. "
            "Use this app to learn, to ask better questions, and to understand concepts — "
            "but never as a final decision-maker."
        )
        text.setWordWrap(True)
        text.setStyleSheet("color:#374151; font-size:12px;")

        c.addWidget(title)
        c.addSpacing(8)
        c.addWidget(text)
        layout.addWidget(card)
        layout.addStretch()

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)


# ---------- Main Window ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Breast Cancer AI Lab (Educational)")
        self.resize(1200, 720)
        self.setWindowIcon(QIcon())  # You can set a real icon here

        self.setStyleSheet("""
            QMainWindow {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #fdf2ff,
                    stop:0.4 #e0f2fe,
                    stop:1 #fef9c3
                );
            }
            QPushButton#primaryButton {
                background-color: #fb7185;
                color: white;
                border-radius: 999px;
                padding: 8px 18px;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover {
                background-color: #f97373;
            }
        """)

        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: rgba(255,255,255,220);
                border-radius: 20px;
            }
            QFrame QLabel {
                color:#4b5563;
            }
        """)
        s_layout = QVBoxLayout(sidebar)
        s_layout.setSpacing(8)

        title = QLabel("BCare AI")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color:#111827;")
        s_layout.addWidget(title)
        s_layout.addWidget(QLabel("Educational Desktop Lab"))
        s_layout.addSpacing(16)

        self.buttons: List[QPushButton] = []
        pages = [
            ("Home", 0),
            ("Risk", 1),
            ("Diagnosis", 2),
            ("Prognosis", 3),
            ("Federated", 4),
            ("XAI", 5),
            ("Prevention", 6),
        ]
        for text, idx in pages:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    text-align: left;
                    padding: 8px 12px;
                    border-radius: 12px;
                    color:#4b5563;
                }
                QPushButton:hover {
                    background-color: rgba(129, 140, 248, 60);
                }
                QPushButton:checked {
                    background-color: rgba(129, 140, 248, 120);
                    color:white;
                }
            """)
            btn.clicked.connect(lambda checked, i=idx: self.on_nav_clicked(i))
            s_layout.addWidget(btn)
            self.buttons.append(btn)

        s_layout.addStretch()
        root_layout.addWidget(sidebar)

        # Stack
        self.stack = AnimatedStackedWidget()
        self.stack.addWidget(HomePage())        # 0
        self.stack.addWidget(RiskPage())        # 1
        self.stack.addWidget(DiagnosisPage())   # 2
        self.stack.addWidget(PrognosisPage())   # 3
        self.stack.addWidget(FederatedPage())   # 4
        self.stack.addWidget(XaiPage())         # 5
        self.stack.addWidget(PreventionPage())  # 6

        root_layout.addWidget(self.stack, 1)

        self.setCentralWidget(central)
        self.buttons[0].setChecked(True)

    @pyqtSlot(int)
    def on_nav_clicked(self, index: int):
        for i, b in enumerate(self.buttons):
            b.setChecked(i == index)
        self.stack.slide_to_index(index)


# ---------- Entry Point ----------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Breast Cancer AI Lab (Educational)")
    app.setFont(QFont("Segoe UI", 10))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
