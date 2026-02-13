from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsLineItem
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QPolygonF, QBrush
import gdstk

class UniversalGDSViewer(QGraphicsView):
    """
    通用 GDS 查看器
    Mode 0: 纯浏览
    Mode 1: Lens 偏移测量 (点击拖拽 -> 计算相对于 Cell 中心的偏移)
    Mode 2: Shot 区域选择 (Ctrl+拖拽 -> 返回绝对坐标和尺寸)
    """
    # 信号定义：
    # Lens 模式: offset_x, offset_y, height
    regionSelectedLens = pyqtSignal(float, float, float) 
    # Shot 模式: center_x, center_y, width, height
    regionSelectedShot = pyqtSignal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QColor(30, 30, 30))
        self.scale(1, -1) # GDS 坐标系反转

        self.cell_bbox = None
        self.cell_center = (0, 0)
        self.mode = 'view' # view, lens_select, shot_select
        
        self.drawing = False
        self.start_point = None
        self.current_rect_item = None

    def load_cell(self, cell):
        self.scene.clear()
        self.current_rect_item = None
        
        # 展平以便显示
        temp_cell = gdstk.Cell("TEMP")
        temp_cell.add(gdstk.Reference(cell))
        flat_cell = temp_cell.flatten()
        
        bbox = flat_cell.bounding_box()
        if bbox is None: return

        min_x, min_y = bbox[0]
        max_x, max_y = bbox[1]
        self.cell_bbox = (min_x, min_y, max_x, max_y)
        self.cell_center = ((min_x + max_x)/2, (min_y + max_y)/2)

        # 绘制坐标原点/中心辅助线
        cx, cy = self.cell_center
        line_len = (max_x - min_x) * 0.2
        pen_center = QPen(QColor(0, 255, 0), 0)
        self.scene.addLine(cx - line_len, cy, cx + line_len, cy, pen_center)
        self.scene.addLine(cx, cy - line_len, cx, cy + line_len, pen_center)

        # 绘制 Polygons
        pen_poly = QPen(QColor(200, 200, 255), 0)
        brush_poly = QBrush(QColor(200, 200, 255, 50))
        
        for poly in flat_cell.polygons:
            pts = [QPointF(p[0], p[1]) for p in poly.points]
            qpoly = QGraphicsPolygonItem(QPolygonF(pts))
            qpoly.setPen(pen_poly)
            qpoly.setBrush(brush_poly)
            self.scene.addItem(qpoly)

        self.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)

    def set_mode(self, mode_name):
        self.mode = mode_name
        if mode_name == 'view':
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, event):
        # Lens 模式直接左键，Shot 模式需要 Ctrl (为了保持与原版操作习惯一致，也可统一)
        is_lens_trigger = (self.mode == 'lens_select' and event.button() == Qt.LeftButton)
        is_shot_trigger = (self.mode == 'shot_select' and event.modifiers() == Qt.ControlModifier and event.button() == Qt.LeftButton)

        if is_lens_trigger or is_shot_trigger:
            self.drawing = True
            self.start_point = self.mapToScene(event.pos())
            if self.current_rect_item:
                self.scene.removeItem(self.current_rect_item)
            
            self.current_rect_item = QGraphicsRectItem()
            self.current_rect_item.setPen(QPen(QColor(255, 0, 0), 0, Qt.DashLine))
            self.current_rect_item.setBrush(QBrush(QColor(255, 0, 0, 80)))
            self.scene.addItem(self.current_rect_item)
            self.update_rect(self.start_point)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drawing:
            self.update_rect(self.mapToScene(event.pos()))
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drawing:
            self.drawing = False
            self.emit_metrics()
            # Lens 模式画完通常切回 View，Shot 模式保持
            if self.mode == 'lens_select':
                self.set_mode('view')
        else:
            super().mouseReleaseEvent(event)

    def update_rect(self, end_point):
        if not self.start_point: return
        rect = QRectF(self.start_point, end_point).normalized()
        self.current_rect_item.setRect(rect)

    def emit_metrics(self):
        if not self.current_rect_item: return
        rect = self.current_rect_item.rect()
        
        if self.mode == 'lens_select':
            # 返回相对于 Cell 中心的偏移
            off_x = rect.center().x() - self.cell_center[0]
            off_y = rect.center().y() - self.cell_center[1]
            self.regionSelectedLens.emit(off_x, off_y, rect.height())
        
        elif self.mode == 'shot_select':
            # 返回绝对坐标
            self.regionSelectedShot.emit(
                rect.center().x(), rect.center().y(), 
                rect.width(), rect.height()
            )

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)