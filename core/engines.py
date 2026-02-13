import os
import math
import io  # 新增：用于内存文件处理
import gdstk
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Rectangle as MplRect, ConnectionPatch

# 确保 matplotlib 后端正确
matplotlib.use('Agg')

class BaseEngine:
    """所有引擎的基类，处理通用的文件读取"""
    def __init__(self):
        self.lib = None
        self.cells_map = {}

    def load_lib(self, path):
        self.lib = gdstk.read_gds(path)
        self.cells_map = {c.name: c for c in self.lib.cells}
        return sorted(list(self.cells_map.keys()))

    def save_lib(self, path):
        if self.lib:
            self.lib.write_gds(path)

class LensEngine(BaseEngine):
    """Lens 自动编号的核心算法"""
    def process(self, parent_name, child_name, layer, datatype, size, offset, 
                tolerance, mode, sort_dir, out_path, digit_width=4):
        
        if parent_name not in self.cells_map or child_name not in self.cells_map:
            raise ValueError("Cell 未找到")

        cell_a = self.cells_map[parent_name] 
        cell_b = self.cells_map[child_name]  

        bbox = cell_b.bounding_box()
        local_center = ((bbox[0][0]+bbox[1][0])/2, (bbox[0][1]+bbox[1][1])/2) if bbox else (0,0)

        instances = []
        for ref in cell_a.references:
            r_name = ref.cell.name if isinstance(ref.cell, gdstk.Cell) else ref.cell
            if r_name == child_name:
                abs_x = ref.origin[0] + local_center[0]
                abs_y = ref.origin[1] + local_center[1]
                instances.append({'ref': ref, 'x': abs_x, 'y': abs_y, 'label': ''})

        if not instances:
            raise ValueError("没有找到实例")

        if mode == "row_col":
            all_x = sorted([i['x'] for i in instances])
            all_y = sorted([i['y'] for i in instances])
            def get_unique(coords):
                if not coords: return []
                u = [coords[0]]
                for c in coords[1:]:
                    if c - u[-1] > tolerance: u.append(c)
                return u
            unique_x = get_unique(all_x)
            unique_y = get_unique(all_y)
            for inst in instances:
                r_idx = next((i+1 for i, u in enumerate(unique_y) if abs(inst['y'] - u) <= tolerance), -1)
                c_idx = next((i+1 for i, u in enumerate(unique_x) if abs(inst['x'] - u) <= tolerance), -1)
                inst['label'] = f"{r_idx}-{c_idx}"
        else:
            if sort_dir == 'y_first':
                instances.sort(key=lambda i: (round(i['y'] / tolerance), i['x']))
            else:
                instances.sort(key=lambda i: (round(i['x'] / tolerance), i['y']))
            for idx, inst in enumerate(instances):
                inst['label'] = f"{idx + 1:0{digit_width}d}"

        for inst in instances:
            text = inst['label']
            target_x = inst['x'] + offset[0]
            target_y = inst['y'] + offset[1]
            polys = gdstk.text(text, size=size, position=(0,0), layer=layer, datatype=datatype)
            min_tx, min_ty, max_tx, max_ty = float('inf'), float('inf'), float('-inf'), float('-inf')
            valid = False
            for p in polys:
                pb = p.bounding_box()
                if pb:
                    valid = True
                    min_tx, min_ty = min(min_tx, pb[0][0]), min(min_ty, pb[0][1])
                    max_tx, max_ty = max(max_tx, pb[1][0]), max(max_ty, pb[1][1])
            if not valid: continue
            shift_x = target_x - (min_tx + max_tx)/2
            shift_y = target_y - (min_ty + max_ty)/2
            for p in polys:
                p.translate(shift_x, shift_y)
                cell_a.add(p)
        self.save_lib(out_path)

class PadEngine(BaseEngine):
    """Pad 信息提取核心算法"""
    def run_analysis(self, gds_path, cell_name, layer, datatype, output_path, temp_img_path):
        lib = gdstk.read_gds(gds_path)
        cell_dict = {cell.name: cell for cell in lib.cells}
        if cell_name not in cell_dict: raise ValueError(f"Cell '{cell_name}' 未在库中找到。")
        cell = cell_dict[cell_name]
        flat_cell = cell.flatten()
        raw_data_with_poly = []
        for poly in flat_cell.polygons:
            if poly.layer == layer and poly.datatype == datatype:
                bbox = poly.bounding_box()
                if bbox:
                    min_x, min_y = bbox[0]
                    max_x, max_y = bbox[1]
                    cx, cy = (min_x + max_x)/2, (min_y + max_y)/2
                    w, h = max_x - min_x, max_y - min_y
                    raw_data_with_poly.append({'data': {'cx': cx, 'cy': cy, 'w': w, 'h': h}, 'points': poly.points})
        if not raw_data_with_poly: raise ValueError("未找到数据。")
        raw_data_with_poly.sort(key=lambda item: (-round(item['data']['cy'], 3), item['data']['cx']))
        data_list = [item['data'] for item in raw_data_with_poly]
        polygons_to_draw = [item['points'] for item in raw_data_with_poly]
        self._generate_plot(data_list, polygons_to_draw, temp_img_path)
        self._write_excel(data_list, output_path, temp_img_path)
        return len(data_list)

    def _generate_plot(self, data_list, polygons, img_path):
        fig, ax = plt.subplots(figsize=(10, 10))
        for points in polygons:
            mpl_poly = MplPolygon(points, closed=True, facecolor='skyblue', edgecolor='blue', alpha=0.3, linewidth=0.5)
            ax.add_patch(mpl_poly)
        xs = [d['cx'] for d in data_list]
        ys = [d['cy'] for d in data_list]
        ax.scatter(xs, ys, c='red', s=60, marker='o', zorder=10)
        if len(data_list) < 3000: 
            for i, (x, y) in enumerate(zip(xs, ys), start=1):
                ax.text(x, y, str(i), fontsize=16, color='black', weight='bold', zorder=15)
        ax.set_title(f"Pad Inspection (Count: {len(data_list)})")
        ax.set_aspect('equal')
        ax.autoscale_view()
        ax.grid(True, linestyle='--', alpha=0.3)
        plt.savefig(img_path, bbox_inches='tight', dpi=100)
        plt.close(fig)

    def _write_excel(self, data_list, output_path, img_path):
        df = pd.DataFrame(data_list)
        df.index = df.index + 1
        df.index.name = 'Index'
        try:
            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Sheet1')
                worksheet = writer.sheets['Sheet1']
                worksheet.insert_image(1, 8, img_path, {'x_scale': 0.8, 'y_scale': 0.8})
        except PermissionError:
             raise IOError(f"无法写入文件 '{output_path}'。\n请检查该文件是否已在 Excel 中打开？\n如果是，请关闭文件后重试。")

class ShotEngine(BaseEngine):
    """Shot 自动编号核心算法"""
    def process(self, cell_a_name, cell_b_name, text_anchor, text_area, layer, datatype, out_path):
        if cell_a_name not in self.cells_map: raise ValueError(f"{cell_a_name} 不存在")
        cell_a = self.cells_map[cell_a_name]
        instances = []
        for ref in cell_a.references:
            ref_name = ref.cell.name if isinstance(ref.cell, gdstk.Cell) else ref.cell
            if ref_name == cell_b_name:
                sort_x, sort_y = self._transform_point((0,0), ref)
                text_x, text_y = self._transform_point(text_anchor, ref)
                instances.append({'ref': ref, 'sort_x': sort_x, 'sort_y': sort_y, 'text_x': text_x, 'text_y': text_y})
        if not instances: raise ValueError("未找到引用")
        
        all_sx = [i['sort_x'] for i in instances]
        all_sy = [i['sort_y'] for i in instances]
        avg_x, avg_y = sum(all_sx)/len(all_sx), sum(all_sy)/len(all_sy)
        center_inst = min(instances, key=lambda i: (i['sort_x']-avg_x)**2 + (i['sort_y']-avg_y)**2)
        
        prec = 3
        u_x = sorted(list(set([round(x, prec) for x in all_sx])))
        u_y = sorted(list(set([round(y, prec) for y in all_sy])))
        base_ix = u_x.index(round(center_inst['sort_x'], prec))
        base_iy = u_y.index(round(center_inst['sort_y'], prec))

        l_w, l_h = text_area
        char_aspect = 0.6
        for inst in instances:
            ix = u_x.index(round(inst['sort_x'], prec)) - base_ix
            iy = u_y.index(round(inst['sort_y'], prec)) - base_iy
            idx_str = f"({ix},{iy})"
            mag = inst['ref'].magnification or 1.0
            size = min(l_h * 0.9, (l_w * 0.9) / (len(idx_str) * char_aspect)) * mag
            text_polys = gdstk.text(idx_str, size, (0,0), layer=layer, datatype=datatype)
            bbox = gdstk.Cell('temp').add(*text_polys).bounding_box()
            if bbox:
                tcx, tcy = (bbox[0][0]+bbox[1][0])/2, (bbox[0][1]+bbox[1][1])/2
                dx, dy = inst['text_x'] - tcx, inst['text_y'] - tcy
                for p in text_polys:
                    p.translate(dx, dy)
                    cell_a.add(p)
        self.save_lib(out_path)

    def _transform_point(self, point, reference):
        px, py = point
        origin = reference.origin
        rotation = reference.rotation
        magnification = reference.magnification or 1.0
        x_reflection = reference.x_reflection
        if x_reflection: py = -py
        px *= magnification
        py *= magnification
        if rotation is not None and rotation != 0:
            c, s = math.cos(rotation), math.sin(rotation)
            px, py = px*c - py*s, px*s + py*c
        return (px + origin[0], py + origin[1])

# --- Cell Info 引擎 (完美对齐 + 坐标轴修复版) ---
class CellInfoEngine(BaseEngine):
    """Cell 信息提取与对齐图生成引擎"""

    def get_child_names(self, parent_name):
        if parent_name not in self.cells_map: return []
        parent = self.cells_map[parent_name]
        children = set()
        for ref in parent.references:
            r_name = ref.cell.name if isinstance(ref.cell, gdstk.Cell) else ref.cell
            children.add(r_name)
        return sorted(list(children))

    def process(self, parent_name, target_children, output_path, temp_img_path=None):
        # 注意：temp_img_path 参数保留是为了兼容，但内部逻辑不再使用它保存文件
        
        if parent_name not in self.cells_map:
            raise ValueError("Parent Cell 不存在")
        
        parent = self.cells_map[parent_name]
        
        # 1. 获取 Parent 的 BBox
        parent_bbox = parent.bounding_box()
        if parent_bbox is None:
            parent_bbox = [[0, 0], [0, 0]]
            
        data_list = []
        seen_cells = set() 

        # 2. 提取数据
        all_instances = []
        for ref in parent.references:
            r_name = ref.cell.name if isinstance(ref.cell, gdstk.Cell) else ref.cell
            if r_name in target_children:
                bbox = ref.bounding_box()
                if bbox is None: continue
                cx = (bbox[0][0] + bbox[1][0]) / 2
                cy = (bbox[0][1] + bbox[1][1]) / 2
                w = bbox[1][0] - bbox[0][0]
                h = bbox[1][1] - bbox[0][1]
                
                all_instances.append({
                    'CellName': r_name,
                    'Center_X': cx, 
                    'Center_Y': cy, 
                    'Width': w, 
                    'Height': h
                })

        # 排序：Top -> Bottom
        all_instances.sort(key=lambda x: (-round(x['Center_Y'], 3), x['Center_X']))

        # 去重
        for item in all_instances:
            if item['CellName'] not in seen_cells:
                seen_cells.add(item['CellName'])
                data_list.append(item)

        if not data_list:
            raise ValueError("未找到指定的子 Cell 实例")

        # 3. 准备数据
        final_plot_data = []
        for i, item in enumerate(data_list):
            idx = i + 1 
            item['Index'] = idx
            final_plot_data.append({
                'id': idx,
                'name': item['CellName'],
                'cx': item['Center_X'],
                'cy': item['Center_Y'],
                'w': item['Width'],
                'h': item['Height']
            })

        # 4. 设定 Excel 行高参数 (Points)
        ROW_HEIGHT_PT = 30 
        
        # 5. 生成对齐图 (返回 bytes buffer)
        image_buffer = self._generate_aligned_plot(final_plot_data, parent_bbox, ROW_HEIGHT_PT)
        
        # 6. 写入 Excel
        self._write_excel(data_list, output_path, image_buffer, ROW_HEIGHT_PT)
        
        return len(data_list)

    def _generate_aligned_plot(self, plot_items, parent_bbox, row_height_pt):
        """
        生成一张绝对对齐的图。
        """
        num_rows = len(plot_items)
        dpi = 100
        
        # --- 尺寸计算关键 ---
        # 数据区域高度 = 行数 * 行高
        data_height_inch = (num_rows * row_height_pt) / 72.0
        
        # 底部留白给 X 轴 (例如 0.8 英寸，约 80px)
        axis_margin_inch = 0.8
        
        # 总高度
        total_height_inch = data_height_inch + axis_margin_inch
        
        # 宽度 (保持足够大)
        total_width_inch = 12 
        
        fig = plt.figure(figsize=(total_width_inch, total_height_inch), dpi=dpi)
        
        # 使用 subplots_adjust 来强制定义“数据区域”
        # 我们希望 top=1.0 (顶端无缝), bottom = axis_margin / total_height
        # 这样 top - bottom 的高度比例正好对应 data_height_inch
        
        bottom_ratio = axis_margin_inch / total_height_inch
        plt.subplots_adjust(left=0, right=0.92, top=1.0, bottom=bottom_ratio, wspace=0.0)
        
        # 定义 GridSpec (左右分割：锚点区 vs 绘图区)
        gs = fig.add_gridspec(1, 2, width_ratios=[1, 25])
        ax_left = fig.add_subplot(gs[0])
        ax_layout = fig.add_subplot(gs[1])
        
        # --- 1. 左侧锚点轴 ---
        ax_left.set_axis_off()
        ax_left.set_ylim(num_rows, 0) # 0在顶部
        ax_left.set_xlim(0, 1)

        # 颜色映射
        unique_names = list(set(p['name'] for p in plot_items))
        colors = plt.cm.get_cmap('tab10', len(unique_names))
        color_map = {name: colors(i) for i, name in enumerate(unique_names)}

        shrink_amount = 10.0 
        
        # --- 2. 绘制 Parent BBox ---
        p_min_x, p_min_y = parent_bbox[0]
        p_max_x, p_max_y = parent_bbox[1]
        p_w = p_max_x - p_min_x
        p_h = p_max_y - p_min_y
        
        rect_parent = MplRect((p_min_x, p_min_y), p_w, p_h,
                              linewidth=1.0, edgecolor='black', linestyle='--', 
                              facecolor='none', label='Top Cell Extent')
        ax_layout.add_patch(rect_parent)

        # --- 3. 绘制子 Cells ---
        for i, item in enumerate(plot_items):
            anchor_y = i + 0.5 
            
            color = color_map[item['name']]
            cx, cy = item['cx'], item['cy']
            w, h = item['w'], item['h']
            
            # Layout Rectangle
            draw_w = w - 2 * shrink_amount if w > 2.5 * shrink_amount else w
            draw_h = h - 2 * shrink_amount if h > 2.5 * shrink_amount else h
            min_x = cx - draw_w / 2
            min_y = cy - draw_h / 2
            
            rect = MplRect((min_x, min_y), draw_w, draw_h, 
                           linewidth=2, edgecolor=color, facecolor='none')
            ax_layout.add_patch(rect)
            
            # Layout Center Dot
            ax_layout.scatter([cx], [cy], color=color, s=40, zorder=10)
            
            # Left Anchor Dot
            ax_left.scatter([0.9], [anchor_y], color=color, s=40, zorder=10)
            
            # Connection Line
            con = ConnectionPatch(
                xyA=(cx, cy), coordsA=ax_layout.transData,
                xyB=(0.9, anchor_y), coordsB=ax_left.transData,
                color=color,
                arrowstyle="-", 
                linestyle="--",
                linewidth=0.8
            )
            fig.add_artist(con)
            
            # Label
            ax_layout.text(min_x, max(min_y, cy), item['name'], color=color, fontsize=8, alpha=0.7)

        # --- 4. 坐标轴优化 ---
        ax_layout.set_aspect('equal')
        ax_layout.grid(True, which='both', linestyle=':', alpha=0.5, color='gray')
        
        # 坐标轴标签
        ax_layout.set_xlabel('X Coordinate (um)', fontsize=10)
        ax_layout.set_ylabel('Y Coordinate (um)', fontsize=10)
        
        # 将 Y 轴移到右侧，避免遮挡左侧对齐点
        ax_layout.yaxis.tick_right()
        ax_layout.yaxis.set_label_position("right")
        
        # 自动缩放范围
        margin_x = p_w * 0.1 if p_w > 0 else 100
        margin_y = p_h * 0.1 if p_h > 0 else 100
        ax_layout.set_xlim(p_min_x - margin_x, p_max_x + margin_x)
        ax_layout.set_ylim(p_min_y - margin_y, p_max_y + margin_y)
        
        # 保存到内存流
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=dpi) # 这里不需要 bbox_inches='tight'，因为我们手动控制了 layout
        plt.close(fig)
        buf.seek(0)
        return buf

    def _write_excel(self, data, output_path, image_buffer, row_height_pt):
        df = pd.DataFrame(data)
        cols = ['Index', 'CellName', 'Center_X', 'Center_Y', 'Width', 'Height']
        df = df[cols]
        
        try:
            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                sheet_name = 'CellInfo'
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                
                workbook = writer.book
                worksheet = writer.sheets[sheet_name]
                
                header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
                cell_fmt = workbook.add_format({'align': 'center', 'valign': 'vcenter'})
                
                # 写表头
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_fmt)
                
                # 设置数据行高
                for i in range(len(data)):
                    worksheet.set_row(i + 1, row_height_pt, cell_fmt)
                
                # 列宽
                worksheet.set_column('A:A', 6)
                worksheet.set_column('B:B', 25)
                worksheet.set_column('C:F', 12)
                
                # 插入内存图片
                # 使用 dummy filename，通过 image_data 传递流
                worksheet.insert_image(1, 7, 'plot.png', {
                    'image_data': image_buffer,
                    'x_offset': 0, 
                    'y_offset': 0, 
                    'x_scale': 1.0, 
                    'y_scale': 1.0,
                    'object_position': 1 
                })
                
                worksheet.write('G1', 'Visual ->', header_fmt)
                
        except PermissionError:
            raise IOError(f"无法写入文件 '{output_path}'。\n请检查该文件是否已在 Excel 中打开？\n如果是，请关闭文件后重试。")