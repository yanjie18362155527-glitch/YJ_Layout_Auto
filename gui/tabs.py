import os
import traceback
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QFileDialog, QComboBox, QSpinBox, 
                             QDoubleSpinBox, QGroupBox, QProgressBar, QTextEdit, 
                             QMessageBox, QDialog, QSplitter, QListWidget, QListWidgetItem,
                             QAbstractItemView)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# 导入我们的自定义模块
from core.engines import LensEngine, PadEngine, ShotEngine, CellInfoEngine
from gui.widgets import UniversalGDSViewer

# --- Worker for Pad Threading ---
class PadWorker(QThread):
    log_signal = pyqtSignal(str)
    finish_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, engine, **kwargs):
        super().__init__()
        self.engine = engine
        self.kwargs = kwargs

    def run(self):
        try:
            self.log_signal.emit("开始处理...")
            count = self.engine.run_analysis(**self.kwargs)
            self.finish_signal.emit(f"成功处理 {count} 个目标。")
        except Exception as e:
            self.error_signal.emit(traceback.format_exc())

# --- Tab 1: Lens ---
class LensTab(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = LensEngine()
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        
        # Left Control
        left_panel = QWidget()
        l_layout = QVBoxLayout(left_panel)
        left_panel.setMaximumWidth(400)
        
        # File Group
        grp_file = QGroupBox("1. 文件与 Cell")
        f_layout = QVBoxLayout()
        self.btn_load = QPushButton("选择 GDS")
        self.btn_load.clicked.connect(self.load_gds)
        self.lbl_file = QLabel("未选择")
        self.combo_parent = QComboBox()
        self.combo_child = QComboBox()
        self.combo_child.currentIndexChanged.connect(self.on_child_select)
        f_layout.addWidget(self.btn_load)
        f_layout.addWidget(self.lbl_file)
        f_layout.addWidget(QLabel("父 Cell (阵列):"))
        f_layout.addWidget(self.combo_parent)
        f_layout.addWidget(QLabel("子 Cell (单元):"))
        f_layout.addWidget(self.combo_child)
        grp_file.setLayout(f_layout)
        
        # Interact Group
        grp_interact = QGroupBox("2. 交互设置")
        i_layout = QVBoxLayout()
        self.btn_draw = QPushButton("点击框选区域")
        self.btn_draw.clicked.connect(self.start_draw)
        self.btn_draw.setEnabled(False)
        
        h_size = QHBoxLayout()
        self.spin_size = QDoubleSpinBox()
        self.spin_size.setRange(0, 1e6)
        self.spin_size.setValue(50)
        h_size.addWidget(QLabel("字号:"))
        h_size.addWidget(self.spin_size)
        
        h_off = QHBoxLayout()
        self.spin_off_x = QDoubleSpinBox()
        self.spin_off_x.setRange(-1e6, 1e6)
        self.spin_off_y = QDoubleSpinBox()
        self.spin_off_y.setRange(-1e6, 1e6)
        h_off.addWidget(QLabel("Off X:"))
        h_off.addWidget(self.spin_off_x)
        h_off.addWidget(QLabel("Y:"))
        h_off.addWidget(self.spin_off_y)
        
        i_layout.addWidget(self.btn_draw)
        i_layout.addLayout(h_size)
        i_layout.addLayout(h_off)
        grp_interact.setLayout(i_layout)
        
        # Config Group
        grp_conf = QGroupBox("3. 参数配置")
        c_layout = QVBoxLayout()
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["行列坐标 (R-C)", "顺序索引 (1, 2...)"])
        self.combo_mode.currentIndexChanged.connect(self.update_state)
        
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["Y 优先", "X 优先"])
        
        self.spin_digits = QSpinBox()
        self.spin_digits.setValue(4)
        
        self.spin_tol = QDoubleSpinBox()
        self.spin_tol.setValue(1.0)
        
        self.spin_layer = QSpinBox()
        self.spin_layer.setValue(66)
        self.spin_dt = QSpinBox()
        self.spin_dt.setValue(0)
        
        c_layout.addWidget(QLabel("模式:"))
        c_layout.addWidget(self.combo_mode)
        c_layout.addWidget(QLabel("排序方向:"))
        c_layout.addWidget(self.combo_sort)
        c_layout.addWidget(QLabel("位数:"))
        c_layout.addWidget(self.spin_digits)
        c_layout.addWidget(QLabel("容差:"))
        c_layout.addWidget(self.spin_tol)
        
        h_lay = QHBoxLayout()
        h_lay.addWidget(QLabel("L:"))
        h_lay.addWidget(self.spin_layer)
        h_lay.addWidget(QLabel("D:"))
        h_lay.addWidget(self.spin_dt)
        c_layout.addLayout(h_lay)
        grp_conf.setLayout(c_layout)
        
        # Run
        self.line_out = QLineEdit("output_lens.gds")
        self.btn_run = QPushButton("生成 GDS")
        self.btn_run.clicked.connect(self.run)
        
        l_layout.addWidget(grp_file)
        l_layout.addWidget(grp_interact)
        l_layout.addWidget(grp_conf)
        l_layout.addWidget(QLabel("输出:"))
        l_layout.addWidget(self.line_out)
        l_layout.addWidget(self.btn_run)
        l_layout.addStretch()
        
        # Right View
        self.viewer = UniversalGDSViewer()
        self.viewer.regionSelectedLens.connect(self.on_region_selected)
        
        layout.addWidget(left_panel)
        layout.addWidget(self.viewer)
        
        self.update_state()

    def load_gds(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open GDS", "", "*.gds")
        if path:
            try:
                names = self.engine.load_lib(path)
                self.combo_parent.clear()
                self.combo_child.clear()
                self.combo_parent.addItems(names)
                self.combo_child.addItems(names)
                self.lbl_file.setText(os.path.basename(path))
                
                # Smart default
                if "D53Z_V1" in names: self.combo_parent.setCurrentText("D53Z_V1")
                if "lens_fan" in names: self.combo_child.setCurrentText("lens_fan")
                
                self.btn_draw.setEnabled(True)
                self.on_child_select()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def on_child_select(self):
        c_name = self.combo_child.currentText()
        if c_name and c_name in self.engine.cells_map:
            self.viewer.load_cell(self.engine.cells_map[c_name])

    def start_draw(self):
        self.viewer.set_mode('lens_select')

    def on_region_selected(self, x, y, h):
        self.spin_off_x.setValue(x)
        self.spin_off_y.setValue(y)
        self.spin_size.setValue(h)

    def update_state(self):
        is_seq = "顺序" in self.combo_mode.currentText()
        self.combo_sort.setEnabled(is_seq)
        self.spin_digits.setEnabled(is_seq)

    def run(self):
        try:
            mode = "row_col" if "行列" in self.combo_mode.currentText() else "index"
            sort = "y_first" if "Y" in self.combo_sort.currentText() else "x_first"
            
            self.engine.process(
                self.combo_parent.currentText(),
                self.combo_child.currentText(),
                self.spin_layer.value(),
                self.spin_dt.value(),
                self.spin_size.value(),
                (self.spin_off_x.value(), self.spin_off_y.value()),
                self.spin_tol.value(),
                mode, sort,
                self.line_out.text(),
                self.spin_digits.value()
            )
            QMessageBox.information(self, "Success", "完成!")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# --- Tab 2: Pad Info ---
class PadTab(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = PadEngine()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Input
        grp_in = QGroupBox("输入设置")
        form = QVBoxLayout()
        
        h1 = QHBoxLayout()
        self.line_gds = QLineEdit()
        btn_gds = QPushButton("...")
        btn_gds.clicked.connect(self.browse_gds)
        h1.addWidget(QLabel("GDS:"))
        h1.addWidget(self.line_gds)
        h1.addWidget(btn_gds)
        
        h2 = QHBoxLayout()
        self.combo_cell = QComboBox()
        h2.addWidget(QLabel("Cell:"))
        h2.addWidget(self.combo_cell)
        
        h3 = QHBoxLayout()
        self.spin_l = QSpinBox()
        self.spin_l.setValue(9)
        self.spin_d = QSpinBox()
        self.spin_d.setValue(0)
        h3.addWidget(QLabel("Layer:"))
        h3.addWidget(self.spin_l)
        h3.addWidget(QLabel("Datatype:"))
        h3.addWidget(self.spin_d)
        
        form.addLayout(h1)
        form.addLayout(h2)
        form.addLayout(h3)
        grp_in.setLayout(form)
        
        # Output
        grp_out = QGroupBox("输出")
        h_out = QHBoxLayout()
        self.line_out = QLineEdit(os.path.abspath("result_pad.xlsx"))
        btn_out = QPushButton("保存...")
        btn_out.clicked.connect(self.browse_out)
        h_out.addWidget(self.line_out)
        h_out.addWidget(btn_out)
        grp_out.setLayout(h_out)
        
        self.btn_run = QPushButton("开始处理")
        self.btn_run.clicked.connect(self.run)
        self.btn_run.setFixedHeight(40)
        
        self.txt_log = QTextEdit()
        self.progress = QProgressBar()
        self.progress.hide()
        
        layout.addWidget(grp_in)
        layout.addWidget(grp_out)
        layout.addWidget(self.btn_run)
        layout.addWidget(self.txt_log)
        layout.addWidget(self.progress)

    def browse_gds(self):
        path, _ = QFileDialog.getOpenFileName(self, "GDS", "", "*.gds")
        if path:
            self.line_gds.setText(path)
            try:
                # 只是为了读 cell list，轻量读取
                lib = gdstk.read_gds(path)
                names = sorted([c.name for c in lib.cells])
                self.combo_cell.clear()
                self.combo_cell.addItems(names)
                if "DIFF_OPT_V2_1" in names: self.combo_cell.setCurrentText("DIFF_OPT_V2_1")
            except Exception as e:
                self.txt_log.append(f"Load Error: {e}")

    def browse_out(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Excel", self.line_out.text(), "*.xlsx")
        if path: self.line_out.setText(path)

    def run(self):
        self.btn_run.setEnabled(False)
        self.progress.show()
        self.progress.setRange(0,0) # Indeterminate
        self.txt_log.clear()
        
        kwargs = {
            'gds_path': self.line_gds.text(),
            'cell_name': self.combo_cell.currentText(),
            'layer': self.spin_l.value(),
            'datatype': self.spin_d.value(),
            'output_path': self.line_out.text(),
            'temp_img_path': 'temp_pad_view.png'
        }
        
        self.worker = PadWorker(self.engine, **kwargs)
        self.worker.log_signal.connect(self.txt_log.append)
        self.worker.finish_signal.connect(self.on_finish)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def on_finish(self, msg):
        self.progress.hide()
        self.btn_run.setEnabled(True)
        QMessageBox.information(self, "Done", msg)

    def on_error(self, msg):
        self.progress.hide()
        self.btn_run.setEnabled(True)
        self.txt_log.append("Error: " + msg)


# --- Tab 3: Shot Index ---
class ShotTab(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = ShotEngine()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Files
        grp_file = QGroupBox("文件与结构")
        fl = QVBoxLayout()
        h1 = QHBoxLayout()
        self.line_in = QLineEdit()
        btn_in = QPushButton("...")
        btn_in.clicked.connect(self.load_gds)
        h1.addWidget(QLabel("Input:"))
        h1.addWidget(self.line_in)
        h1.addWidget(btn_in)
        
        self.combo_top = QComboBox()
        self.combo_unit = QComboBox()
        
        fl.addLayout(h1)
        fl.addWidget(QLabel("Top Cell:"))
        fl.addWidget(self.combo_top)
        fl.addWidget(QLabel("Unit Cell:"))
        fl.addWidget(self.combo_unit)
        grp_file.setLayout(fl)
        
        # Params
        grp_param = QGroupBox("参数")
        pl = QVBoxLayout()
        
        self.btn_pick = QPushButton("🖐 在 Unit Cell 上框选区域 (Ctrl+Drag)")
        self.btn_pick.clicked.connect(self.open_picker)
        
        h_anchor = QHBoxLayout()
        self.line_anchor = QLineEdit("0, 0")
        h_anchor.addWidget(QLabel("Anchor (x,y):"))
        h_anchor.addWidget(self.line_anchor)
        
        h_area = QHBoxLayout()
        self.line_area = QLineEdit("100, 100")
        h_area.addWidget(QLabel("Area (w,h):"))
        h_area.addWidget(self.line_area)
        
        h_ld = QHBoxLayout()
        self.spin_l = QSpinBox()
        self.spin_l.setValue(100)
        self.spin_d = QSpinBox()
        self.spin_d.setValue(0)
        h_ld.addWidget(QLabel("Layer:"))
        h_ld.addWidget(self.spin_l)
        h_ld.addWidget(QLabel("DT:"))
        h_ld.addWidget(self.spin_d)
        
        pl.addWidget(self.btn_pick)
        pl.addLayout(h_anchor)
        pl.addLayout(h_area)
        pl.addLayout(h_ld)
        grp_param.setLayout(pl)
        
        self.line_out = QLineEdit("output_shot.gds")
        self.btn_run = QPushButton("运行")
        self.btn_run.clicked.connect(self.run)
        
        layout.addWidget(grp_file)
        layout.addWidget(grp_param)
        layout.addWidget(QLabel("Output:"))
        layout.addWidget(self.line_out)
        layout.addWidget(self.btn_run)

    def load_gds(self):
        path, _ = QFileDialog.getOpenFileName(self, "GDS", "", "*.gds")
        if path:
            self.line_in.setText(path)
            try:
                names = self.engine.load_lib(path)
                self.combo_top.clear()
                self.combo_unit.clear()
                self.combo_top.addItems(names)
                self.combo_unit.addItems(names)
                
                if '0MA8_9CUN' in names: self.combo_top.setCurrentText('0MA8_9CUN')
                if '00A_Shot' in names: self.combo_unit.setCurrentText('00A_Shot')
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def open_picker(self):
        if not self.engine.lib: return
        unit_name = self.combo_unit.currentText()
        if unit_name not in self.engine.cells_map: return
        
        # 弹出对话框式选择
        dlg = QDialog(self)
        dlg.setWindowTitle("按住 Ctrl + 左键框选")
        dlg.resize(800, 600)
        l = QVBoxLayout(dlg)
        
        viewer = UniversalGDSViewer()
        viewer.load_cell(self.engine.cells_map[unit_name])
        viewer.set_mode('shot_select')
        
        lbl_info = QLabel("请框选...")
        btn_ok = QPushButton("确认")
        btn_ok.setEnabled(False)
        btn_ok.clicked.connect(dlg.accept)
        
        def on_sel(x, y, w, h):
            lbl_info.setText(f"选中: ({x:.2f}, {y:.2f}) {w:.2f}x{h:.2f}")
            self.temp_sel = (x, y, w, h)
            btn_ok.setEnabled(True)
            
        viewer.regionSelectedShot.connect(on_sel)
        
        l.addWidget(viewer)
        l.addWidget(lbl_info)
        l.addWidget(btn_ok)
        
        if dlg.exec_() == QDialog.Accepted:
            x, y, w, h = self.temp_sel
            self.line_anchor.setText(f"{x:.3f}, {y:.3f}")
            self.line_area.setText(f"{w:.3f}, {h:.3f}")

    def run(self):
        try:
            anchor = [float(x) for x in self.line_anchor.text().split(',')]
            area = [float(x) for x in self.line_area.text().split(',')]
            
            self.engine.process(
                self.combo_top.currentText(),
                self.combo_unit.currentText(),
                anchor, area,
                self.spin_l.value(),
                self.spin_d.value(),
                self.line_out.text()
            )
            QMessageBox.information(self, "Success", "生成成功")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"{traceback.format_exc()}")

# --- Tab 4: Cell Info (New Feature) ---
class CellInfoTab(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = CellInfoEngine()
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        
        # Left Side: Controls
        left_pnl = QWidget()
        l_vbox = QVBoxLayout(left_pnl)
        left_pnl.setMaximumWidth(400)
        
        # 1. Input
        grp_in = QGroupBox("1. GDS 与 Parent")
        form1 = QVBoxLayout()
        self.btn_load = QPushButton("读取 GDS")
        self.btn_load.clicked.connect(self.load_gds)
        self.lbl_path = QLabel("无文件")
        self.combo_parent = QComboBox()
        self.combo_parent.currentIndexChanged.connect(self.on_parent_changed)
        
        form1.addWidget(self.btn_load)
        form1.addWidget(self.lbl_path)
        form1.addWidget(QLabel("选择 Top Cell:"))
        form1.addWidget(self.combo_parent)
        grp_in.setLayout(form1)
        
        # 2. Child Selection
        grp_child = QGroupBox("2. 筛选指定 Child Cells")
        form2 = QVBoxLayout()
        self.list_child = QListWidget()
        self.list_child.setSelectionMode(QAbstractItemView.NoSelection) # 使用Checkbox控制
        form2.addWidget(QLabel("勾选需要提取的子 Cell:"))
        form2.addWidget(self.list_child)
        grp_child.setLayout(form2)
        
        # 3. Output
        grp_out = QGroupBox("3. 执行")
        form3 = QVBoxLayout()
        self.line_out = QLineEdit("result_cell_info.xlsx")
        self.btn_run = QPushButton("提取并生成报告")
        self.btn_run.setFixedHeight(40)
        self.btn_run.clicked.connect(self.run)
        
        form3.addWidget(QLabel("输出 Excel:"))
        form3.addWidget(self.line_out)
        form3.addWidget(self.btn_run)
        grp_out.setLayout(form3)
        
        l_vbox.addWidget(grp_in)
        l_vbox.addWidget(grp_child)
        l_vbox.addWidget(grp_out)
        
        # Right Side: Preview
        self.viewer = UniversalGDSViewer()
        
        layout.addWidget(left_pnl)
        layout.addWidget(self.viewer)

    def load_gds(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open GDS", "", "*.gds")
        if path:
            try:
                names = self.engine.load_lib(path)
                self.lbl_path.setText(os.path.basename(path))
                self.combo_parent.clear()
                self.combo_parent.addItems(names)
                # 尝试智能选择一个看起来像 Top 的
                if len(names) > 0:
                    # 简单启发式：选最大的名字或者包含 TOP 的
                    pass 
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def on_parent_changed(self):
        p_name = self.combo_parent.currentText()
        if not p_name: return
        
        # 1. 更新 Viewer
        if p_name in self.engine.cells_map:
            self.viewer.load_cell(self.engine.cells_map[p_name])
            
        # 2. 更新子 Cell 列表
        children = self.engine.get_child_names(p_name)
        self.list_child.clear()
        for c in children:
            item = QListWidgetItem(c)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list_child.addItem(item)

    def run(self):
        # 获取选中的 targets
        targets = []
        for i in range(self.list_child.count()):
            item = self.list_child.item(i)
            if item.checkState() == Qt.Checked:
                targets.append(item.text())
        
        if not targets:
            QMessageBox.warning(self, "Warning", "请至少勾选一个子 Cell")
            return
            
        try:
            self.btn_run.setEnabled(False)
            self.btn_run.setText("处理中...")
            
            # 由于可能包含绘图，如果数据量大可能会卡，实际项目中建议放到 WorkerThread
            # 这里为了演示简洁直接调用
            count = self.engine.process(
                self.combo_parent.currentText(),
                targets,
                self.line_out.text(),
                "temp_cell_info_plot.png"
            )
            
            QMessageBox.information(self, "Success", f"处理完成！\n共提取 {count} 个实例。\n已保存至 {self.line_out.text()}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", traceback.format_exc())
        finally:
            self.btn_run.setEnabled(True)
            self.btn_run.setText("提取并生成报告")