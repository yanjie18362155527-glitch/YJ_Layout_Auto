from PyQt5.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsPolygonItem, 
                             QGraphicsRectItem, QGraphicsSimpleTextItem)
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QPolygonF, QBrush
import gdstk

class UniversalGDSViewer(QGraphicsView):
    """
    通用 GDS 查看器 (折中优化版)
    1. 本层 Poly: 实体渲染
    2. 子 Cell (Reference): 仅渲染虚线 BBox
    3. 交互: 支持鼠标中心缩放
    """
    # 信号定义
    regionSelectedLens = pyqtSignal(float, float, float) 
    regionSelectedShot = pyqtSignal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QColor(30, 30, 30))
        self.scale(1, -1) # GDS 坐标系反转

        # --- [关键配置] 启用鼠标中心缩放 ---
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        # --------------------------------

        self.cell_bbox = None
        self.cell_center = (0, 0)
        self.mode = 'view'
        
        self.drawing = False
        self.start_point = None
        self.current_rect_item = None

    def load_cell(self, cell):
        """
        加载 Cell: 渲染本层 Poly + 子 Cell 的 BBox
        """
        self.scene.clear()
        self.current_rect_item = None
        
        # 1. 获取数据源
        polys_source = cell.polygons
        refs_source = cell.references  # 获取引用列表
        
        # 2. 计算视图中心
        bbox = cell.bounding_box()
        if bbox is None: 
            if polys_source: # 尝试通过 Poly 估算
                t = gdstk.Cell("TEMP_BBOX")
                t.add(*polys_source[:1000])
                bbox = t.bounding_box()
            
        if bbox is None:
            return

        min_x, min_y = bbox[0]
        max_x, max_y = bbox[1]
        self.cell_bbox = (min_x, min_y, max_x, max_y)
        self.cell_center = ((min_x + max_x)/2, (min_y + max_y)/2)

        # 3. 绘制中心十字
        cx, cy = self.cell_center
        line_len = max((max_x - min_x), (max_y - min_y)) * 0.1
        if line_len == 0: line_len = 100
        pen_center = QPen(QColor(0, 255, 0), 0)
        self.scene.addLine(cx - line_len, cy, cx + line_len, cy, pen_center)
        self.scene.addLine(cx, cy - line_len, cx, cy + line_len, pen_center)

        # 4. 准备画笔
        # 本层多边形: 浅蓝半透明
        pen_poly = QPen(QColor(200, 200, 255), 0)
        brush_poly = QBrush(QColor(200, 200, 255, 50))
        
        # 子 Cell BBox: 黄色虚线，无填充
        pen_ref = QPen(QColor(255, 200, 50), 0)
        pen_ref.setStyle(Qt.DashLine)
        brush_ref = QBrush(Qt.NoBrush)

        self.scene.blockSignals(True)
        
        # --- 5. 渲染本层多边形 (带数量限制) ---
        num_polys = len(polys_source)
        MAX_ITEMS = 5000 
        
        if num_polys > MAX_ITEMS:
            warning_text = QGraphicsSimpleTextItem(f"Polys Limit: {MAX_ITEMS}/{num_polys}")
            warning_text.setBrush(QBrush(QColor(255, 100, 100)))
            scale = line_len * 0.05
            warning_text.setScale(scale if scale > 0 else 1)
            warning_text.setTransform(warning_text.transform().scale(1, -1))
            warning_text.setPos(min_x, max_y)
            self.scene.addItem(warning_text)
            polys_to_draw = polys_source[:MAX_ITEMS]
        else:
            polys_to_draw = polys_source

        for poly in polys_to_draw:
            pts = [QPointF(p[0], p[1]) for p in poly.points]
            qpoly = QGraphicsPolygonItem(QPolygonF(pts))
            qpoly.setPen(pen_poly)
            qpoly.setBrush(brush_poly)
            self.scene.addItem(qpoly)

        # --- 6. 渲染子 Cell BBox (带数量限制) ---
        num_refs = len(refs_source)
        if num_refs > MAX_ITEMS:
            refs_to_draw = refs_source[:MAX_ITEMS]
        else:
            refs_to_draw = refs_source

        for ref in refs_to_draw:
            # gdstk 计算的是 Reference 在父坐标系下的 AABB
            r_bbox = ref.bounding_box()
            if r_bbox:
                rmin_x, rmin_y = r_bbox[0]
                rmax_x, rmax_y = r_bbox[1]
                w = rmax_x - rmin_x
                h = rmax_y - rmin_y
                
                # 绘制矩形框
                rect_item = QGraphicsRectItem(rmin_x, rmin_y, w, h)
                rect_item.setPen(pen_ref)
                rect_item.setBrush(brush_ref)
                
                # 可选: 添加 Tooltip (鼠标悬停显示 Cell 名)
                # name = ref.cell.name if isinstance(ref.cell, gdstk.Cell) else ref.cell
                # rect_item.setToolTip(str(name))
                
                self.scene.addItem(rect_item)

        self.scene.blockSignals(False)
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
            off_x = rect.center().x() - self.cell_center[0]
            off_y = rect.center().y() - self.cell_center[1]
            self.regionSelectedLens.emit(off_x, off_y, rect.height())
        
        elif self.mode == 'shot_select':
            self.regionSelectedShot.emit(
                rect.center().x(), rect.center().y(), 
                rect.width(), rect.height()
            )

    def wheelEvent(self, event):
        # 配合 AnchorUnderMouse 使用
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)