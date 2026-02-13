import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget, QAction, QMessageBox

# 导入 UI 模块
from gui.tabs import LensTab, PadTab, ShotTab, CellInfoTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LayoutAutoTools Pro V2.1 - With Cell Info")
        self.resize(1200, 850)
        self.init_ui()

    def init_ui(self):
        # 菜单栏
        menubar = self.menuBar()
        file_menu = menubar.addMenu('文件')
        exit_act = QAction('退出', self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)
        
        help_menu = menubar.addMenu('帮助')
        about_act = QAction('关于', self)
        about_act.triggered.connect(self.show_about)
        help_menu.addAction(about_act)

        # 核心 Tab 容器
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # 模块化加载 Tab
        self.lens_tab = LensTab()
        self.pad_tab = PadTab()
        self.shot_tab = ShotTab()
        self.info_tab = CellInfoTab()
        
        self.tabs.addTab(self.lens_tab, "1. Lens 自动编号")
        self.tabs.addTab(self.pad_tab, "2. Pad 信息提取")
        self.tabs.addTab(self.shot_tab, "3. Shot 自动编号")
        self.tabs.addTab(self.info_tab, "4. shot内 DB信息提取")

        # 样式优化
        self.tabs.setStyleSheet("""
            QTabBar::tab { height: 40px; width: 150px; font-weight: bold; }
            QTabBar::tab:selected { background-color: #e1f5fe; color: #0277bd; }
        """)

    def show_about(self):
        QMessageBox.about(self, "关于", 
            "版图自动化专家工具集 V2.1\n\n"
            "架构重构版 (MVC Pattern)\n"
            "新增功能: 指定子Cell坐标提取与可视化")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 全局字体设置 (可选)
    # font = app.font()
    # font.setPointSize(10)
    # app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())