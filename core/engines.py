import os
import math
import gdstk
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

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

        cell_a = self.cells_map[parent_name] # Top
        cell_b = self.cells_map[child_name]  # Unit

        # 1. 计算 Cell B 中心 (Local)
        bbox = cell_b.bounding_box()
        local_center = ((bbox[0][0]+bbox[1][0])/2, (bbox[0][1]+bbox[1][1])/2) if bbox else (0,0)

        # 2. 收集实例
        instances = []
        for ref in cell_a.references:
            r_name = ref.cell.name if isinstance(ref.cell, gdstk.Cell) else ref.cell
            if r_name == child_name:
                abs_x = ref.origin[0] + local_center[0]
                abs_y = ref.origin[1] + local_center[1]
                instances.append({'ref': ref, 'x': abs_x, 'y': abs_y, 'label': ''})

        if not instances:
            raise ValueError("没有找到实例")

        # 3. 核心排序与编号逻辑
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
                # 1-based index
                r_idx = next((i+1 for i, u in enumerate(unique_y) if abs(inst['y'] - u) <= tolerance), -1)
                c_idx = next((i+1 for i, u in enumerate(unique_x) if abs(inst['x'] - u) <= tolerance), -1)
                inst['label'] = f"{r_idx}-{c_idx}"
        else:
            # 顺序索引
            if sort_dir == 'y_first':
                # Y 优先：先按 Y 分层 (Bottom -> Top), 同层内按 X (Left -> Right)
                instances.sort(key=lambda i: (round(i['y'] / tolerance), i['x']))
            else:
                instances.sort(key=lambda i: (round(i['x'] / tolerance), i['y']))
                
            for idx, inst in enumerate(instances):
                inst['label'] = f"{idx + 1:0{digit_width}d}"

        # 4. 绘制 Label
        for inst in instances:
            text = inst['label']
            target_x = inst['x'] + offset[0]
            target_y = inst['y'] + offset[1]

            polys = gdstk.text(text, size=size, position=(0,0), layer=layer, datatype=datatype)
            
            # 计算 Text BBox 以居中
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
        # 这里的逻辑从 WorkerThread 中剥离，变为纯函数式调用
        lib = gdstk.read_gds(gds_path)
        cell_dict = {cell.name: cell for cell in lib.cells}
        
        if cell_name not in cell_dict:
            raise ValueError(f"Cell '{cell_name}' 未在库中找到。")
        
        cell = cell_dict[cell_name]
        flat_cell = cell.flatten()
        
        raw_data_with_poly = []
        
        # 提取几何信息
        for poly in flat_cell.polygons:
            if poly.layer == layer and poly.datatype == datatype:
                bbox = poly.bounding_box()
                if bbox:
                    min_x, min_y = bbox[0]
                    max_x, max_y = bbox[1]
                    cx = (min_x + max_x) / 2
                    cy = (min_y + max_y) / 2
                    w = max_x - min_x
                    h = max_y - min_y
                    
                    raw_data_with_poly.append({
                        'data': {'cx': cx, 'cy': cy, 'w': w, 'h': h},
                        'points': poly.points
                    })

        if not raw_data_with_poly:
            raise ValueError("未找到任何符合条件的多边形数据。")

        # 排序：Y (Bottom->Top), X (Left->Right)
        # 注意：原代码逻辑为 -round(cy)，即 Top->Bottom? 
        # 原文: (-round(item['data']['cy'], 3), item['data']['cx'])
        # 负号意味着 Y 越大越靠前 (Top First)。保留原逻辑。
        raw_data_with_poly.sort(key=lambda item: (-round(item['data']['cy'], 3), item['data']['cx']))

        data_list = [item['data'] for item in raw_data_with_poly]
        polygons_to_draw = [item['points'] for item in raw_data_with_poly]

        # 生成图片
        self._generate_plot(data_list, polygons_to_draw, temp_img_path)

        # 生成 Excel
        self._write_excel(data_list, output_path, temp_img_path)
        
        return len(data_list)

    def _generate_plot(self, data_list, polygons, img_path):
        fig, ax = plt.subplots(figsize=(10, 10))
        
        for points in polygons:
            mpl_poly = MplPolygon(points, closed=True, 
                                  facecolor='skyblue', edgecolor='blue', alpha=0.3, linewidth=0.5)
            ax.add_patch(mpl_poly)
        
        xs = [d['cx'] for d in data_list]
        ys = [d['cy'] for d in data_list]
        ax.scatter(xs, ys, c='red', s=60, marker='o', zorder=10)
        
        # 数量少时显示编号
        if len(data_list) < 3000: 
            for i, (x, y) in enumerate(zip(xs, ys), start=1):
                ax.text(x, y, str(i), fontsize=16, color='black', weight='bold', zorder=15)
        
        ax.set_title(f"Sorted Layout Inspection (Count: {len(data_list)})")
        ax.set_aspect('equal')
        ax.autoscale_view()
        ax.grid(True, linestyle='--', alpha=0.3)
        
        plt.savefig(img_path, bbox_inches='tight', dpi=100)
        plt.close(fig)

    def _write_excel(self, data_list, output_path, img_path):
        df = pd.DataFrame(data_list)
        df.index = df.index + 1
        df.index.name = 'Index'
        df['symbol'] = ""
        df['description'] = ""
        df = df[['symbol', 'description', 'cx', 'cy', 'w', 'h']]
        df.columns = ['Symbol', 'Description', 'Center_X', 'Center_Y', 'Width', 'Height']
        
        with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
            sheet_name = 'Sheet1'
            df.to_excel(writer, sheet_name=sheet_name)
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]
            
            worksheet.set_column('A:A', 5)  
            worksheet.set_column('B:C', 15) 
            worksheet.set_column('D:G', 12) 
            worksheet.set_column('H:H', 5) 
            
            worksheet.insert_image(1, 8, img_path, {
                'x_scale': 0.8, 
                'y_scale': 0.8,
                'x_offset': 10,
                'object_position': 1
            })
            worksheet.write('I1', 'Layout Visualization Preview:')

class ShotEngine(BaseEngine):
    """Shot 自动编号核心算法"""
    
    def process(self, cell_a_name, cell_b_name, text_anchor, text_area, layer, datatype, out_path):
        if cell_a_name not in self.cells_map: 
             raise ValueError(f"{cell_a_name} 不存在")
        
        cell_a = self.cells_map[cell_a_name]
        instances = []
        
        # 1. 查找 Reference 并计算变换
        for ref in cell_a.references:
            ref_name = ref.cell.name if isinstance(ref.cell, gdstk.Cell) else ref.cell
            if ref_name == cell_b_name:
                sort_x, sort_y = self._transform_point((0,0), ref)
                text_x, text_y = self._transform_point(text_anchor, ref)
                instances.append({
                    'ref': ref, 'sort_x': sort_x, 'sort_y': sort_y,
                    'text_x': text_x, 'text_y': text_y
                })
        
        if not instances:
            raise ValueError("未找到 Unit Cell 的引用")

        # 2. 确定中心实例以建立基准坐标
        all_sx = [i['sort_x'] for i in instances]
        all_sy = [i['sort_y'] for i in instances]
        avg_x, avg_y = sum(all_sx)/len(all_sx), sum(all_sy)/len(all_sy)
        
        best_dist = float('inf')
        center_inst = instances[0]
        for inst in instances:
            d = (inst['sort_x']-avg_x)**2 + (inst['sort_y']-avg_y)**2
            if d < best_dist:
                best_dist = d
                center_inst = inst
        
        # 3. 建立网格
        prec = 3
        u_x = sorted(list(set([round(x, prec) for x in all_sx])))
        u_y = sorted(list(set([round(y, prec) for y in all_sy])))
        base_ix = u_x.index(round(center_inst['sort_x'], prec))
        base_iy = u_y.index(round(center_inst['sort_y'], prec))

        # 4. 生成编号
        l_w, l_h = text_area
        char_aspect = 0.6
        
        for inst in instances:
            ix = u_x.index(round(inst['sort_x'], prec)) - base_ix
            iy = u_y.index(round(inst['sort_y'], prec)) - base_iy
            
            idx_str = f"({ix},{iy})"
            mag = inst['ref'].magnification or 1.0
            
            size = min(l_h * 0.9, (l_w * 0.9) / (len(idx_str) * char_aspect)) * mag
            
            text_polys = gdstk.text(idx_str, size, (0,0), layer=layer, datatype=datatype)
            
            # 计算文字本身BBox用于居中
            bbox = gdstk.Cell('temp').add(*text_polys).bounding_box()
            if bbox:
                tcx = (bbox[0][0] + bbox[1][0])/2
                tcy = (bbox[0][1] + bbox[1][1])/2
                dx = inst['text_x'] - tcx
                dy = inst['text_y'] - tcy
                for p in text_polys:
                    p.translate(dx, dy)
                    cell_a.add(p)

        self.save_lib(out_path)

    def _transform_point(self, point, reference):
        """仿射变换核心数学公式"""
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