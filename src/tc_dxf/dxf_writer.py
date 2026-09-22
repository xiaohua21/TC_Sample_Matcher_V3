# -*- coding: utf-8 -*-
"""
探槽样品区DXF写入模块 V3
作者：消化

功能：
- 根据样轨投影表数据生成DXF文件
- 支持设置样品厚度、比例尺
- 支持设置样品在左侧或右侧
- 支持设置探槽起点坐标
- 支持样品号标注
- 支持预览
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any


@dataclass
class SampleArea:
    """样品区域"""
    sample_id: str  # 样品号
    s_start: float  # 沿槽起点距离
    t_near: float  # 近侧横向距离（贴槽边，应为0）
    s_end: float  # 沿槽终点距离
    t_far: float  # 远侧横向距离（±厚度）
    color_index: int = 0  # 颜色索引：0=白色, 1=黑色, 2=灰色


@dataclass
class TrenchProfile:
    """探槽剖面数据"""
    trench_id: str  # 探槽编号
    total_length: float  # 探槽总长度
    samples: List[SampleArea] = field(default_factory=list)  # 样品区域列表
    start_x: float = 0.0  # 起点X坐标
    start_y: float = 0.0  # 起点Y坐标
    segments: List[Tuple[float, float]] = field(default_factory=list)  # [(azimuth, length), ...]


class TCDXFWriter:
    """探槽样品区DXF写入器"""

    def __init__(self):
        self.trench_profile: Optional[TrenchProfile] = None
        self.sample_thickness: float = 2.0  # 样品区域厚度（图面距离）
        self.scale: int = 500  # 比例尺 1:scale
        self.sample_side: int = -1  # 样品位置：-1=左侧, +1=右侧
        self.show_labels: bool = True  # 是否显示样品号标注
        self.start_x: float = 0.0  # 起点X坐标
        self.start_y: float = 0.0  # 起点Y坐标
        self.segments: List[Tuple[float, float]] = []  # 探槽段列表
        self.world_points: List[Tuple[float, float]] = []  # 世界坐标点
        self.sample_rects: List[Dict] = []  # 样品矩形列表 [{x1, y1, x4, y4, sample_id, color_index}, ...]
        self.wall_offset: float = 5.0  # 探槽壁偏移距离（垂直于探槽方向）
        self.show_walls: bool = True  # 是否绘制探槽壁轮廓
        self.input_scale: int = 1000  # 输入数据比例尺

    def set_params(self, sample_thickness: float, scale: int, sample_side: int, input_scale: int = 1000):
        """设置参数

        Args:
            sample_thickness: 样品区域厚度（图面距离，单位根据比例尺换算）
            scale: 输出比例尺，如2000表示1:2000
            sample_side: 样品位置，-1=左侧, +1=右侧
            input_scale: 输入数据比例尺，默认1000（1:1000）
        """
        self.sample_thickness = sample_thickness
        self.scale = scale
        self.sample_side = sample_side
        self.input_scale = input_scale

    def set_start_coords(self, start_x: float, start_y: float):
        """设置探槽起点坐标"""
        self.start_x = start_x
        self.start_y = start_y

    def set_move_offset(self, offset_x: float, offset_y: float):
        """设置整体移动偏移量"""
        self.move_offset_x = offset_x
        self.move_offset_y = offset_y

    def set_world_points(self, world_points: List[Tuple[float, float]]):
        """直接设置世界坐标点（用于整体移动后）

        Args:
            world_points: 世界坐标点列表
        """
        self.world_points = world_points
        # 坐标已经是DXF输出的最终坐标，清除move_offset
        self.move_offset_x = 0.0
        self.move_offset_y = 0.0
        # 设置标志表示坐标已经是最终值，DXF输出时跳过缩放
        self._move_applied = True
        self._final_coordinates = True
        # 注意：当_final_coordinates=True时，坐标已经是最终显示坐标，不需要额外缩放
        # _export_scale_factor = 1.0 表示"坐标已经是最终值"
        self._export_scale_factor = 1.0
        # 重置start坐标，因为world_points已包含完整位置信息
        self.start_x = 0.0
        self.start_y = 0.0

        # 设置最小的trench_profile（用于write_dxf_file检查）
        total_length = abs(world_points[-1][0]) if world_points else 0.0
        self.trench_profile = TrenchProfile(
            trench_id=getattr(self, 'trench_id', 'UNKNOWN'),
            total_length=total_length,
            samples=[],
            start_x=0.0,
            start_y=0.0,
            segments=[]
        )
        print(f"[DXF Writer] world_points已设置，长度={len(world_points)}")
        print(f"[DXF Writer] world_points[0]={world_points[0] if world_points else 'empty'}")
        print(f"[DXF Writer] _final_coordinates=True，DXF输出时将跳过缩放")

    def set_sample_rects(self, sample_rects: List):
        """直接设置样品矩形列表（用于整体移动后）

        Args:
            sample_rects: SampleRect对象列表或字典列表
        """
        # 转换为字典格式（如果传入的是SampleRect对象）
        converted_rects = []
        for rect in sample_rects:
            if isinstance(rect, dict):
                converted_rects.append(rect)
            else:
                # 假设是SampleRect对象
                converted_rects.append({
                    'x_start': rect.x_start,
                    'y_start': rect.y_start,
                    'x_end': rect.x_end,
                    'y_end': rect.y_end,
                    'sample_id': rect.sample_id,
                    'color_index': rect.color_index,
                    'start_idx': getattr(rect, 'start_idx', -1),
                    'end_idx': getattr(rect, 'end_idx', -1)
                })
        self.sample_rects = converted_rects
        print(f"[DXF Writer] sample_rects已设置，长度={len(self.sample_rects)}")
        if self.sample_rects:
            first_rect = self.sample_rects[0]
            print(f"[DXF Writer] 第一个矩形: x_start={first_rect['x_start']:.2f}, y_start={first_rect['y_start']:.2f}, x_end={first_rect['x_end']:.2f}, y_end={first_rect['y_end']:.2f}")
            print(f"[DXF Writer] 第一个矩形: start_idx={first_rect.get('start_idx', 'N/A')}, end_idx={first_rect.get('end_idx', 'N/A')}")

    def set_cd_points(self, cd_points: List):
        """直接设置CD线坐标列表（来自Preview的计算结果）

        Args:
            cd_points: CD线坐标列表 [(x, y), ...]
        """
        self.cd_points = cd_points
        print(f"[DXF Writer] cd_points已设置，长度={len(self.cd_points)}")
        if self.cd_points:
            print(f"[DXF Writer] cd_points[0]={self.cd_points[0]}, cd_points[-1]={self.cd_points[-1]}")
        # 写入ENTITIES前的最终检查
        self._cd_points_checked = True

    def set_boundary_perps(self, boundary_perps: Dict):
        """直接设置边界垂线（来自Preview的计算结果）

        Args:
            boundary_perps: 边界垂线字典 {idx: (perp_x, perp_y), ...}
        """
        self._boundary_perps = boundary_perps
        print(f"[DXF Writer] boundary_perps已设置，长度={len(self._boundary_perps)}")
        print(f"[DXF Writer] boundary_perps keys: {list(self._boundary_perps.keys())[:10]}...")

    def set_segments(self, segments: List[Tuple[float, float]]):
        """设置探槽段列表

        Args:
            segments: 探槽段列表 [(azimuth, length), ...]
        """
        self.segments = segments
        self._calculate_world_points()

    def _calculate_world_points(self):
        """计算探槽线的世界坐标点"""
        self.world_points = [(0.0, 0.0)]  # 原点

        x, y = 0.0, 0.0
        for seg_azimuth, seg_length in self.segments:
            rad = math.radians(seg_azimuth)
            dx = seg_length * math.sin(rad)
            dy = seg_length * math.cos(rad)
            x += dx
            y += dy
            self.world_points.append((x, y))

    def s_to_world(self, s: float) -> Tuple[float, float]:
        """沿槽距离 s → 世界坐标"""
        if not self.segments:
            return (s, 0.0)

        acc = 0.0
        for i, (az, L) in enumerate(self.segments):
            if s <= acc + L or i == len(self.segments) - 1:
                local = s - acc
                base_x, base_y = self.world_points[i]
                az_rad = math.radians(az)
                return (base_x + math.sin(az_rad) * local,
                        base_y + math.cos(az_rad) * local)
            acc += L

        return self.world_points[-1] if self.world_points else (s, 0.0)

    def azimuth_at(self, s: float) -> float:
        """沿槽距离 s → 该段方位角"""
        if not self.segments:
            return 0.0

        acc = 0.0
        for i, (az, L) in enumerate(self.segments):
            if s <= acc + L or i == len(self.segments) - 1:
                return az
            acc += L

        return self.segments[-1][0] if self.segments else 0.0

    def st_to_world(self, s: float, t: float) -> Tuple[float, float]:
        """展开坐标 (s, t) → 世界坐标"""
        base_x, base_y = self.s_to_world(s)
        az_rad = math.radians(self.azimuth_at(s))

        perp_x = -math.cos(az_rad)
        perp_y = math.sin(az_rad)

        return (base_x + perp_x * t,
                base_y + perp_y * t)

    def load_from_projection_data(self, trench_id: str, projection_data: List[Dict[str, Any]],
                                 azimuth: float = 0.0, segments: List[Tuple[float, float]] = None):
        """从样轨投影表数据加载

        直接使用投影表的X,Y坐标，不重新计算。
        样品矩形使用相邻样品的端点连线来计算切线方向。

        Args:
            trench_id: 探槽编号
            projection_data: 投影表数据列表，每项包含样号、X坐标、Y坐标、样长等
            azimuth: 探槽方位角（已废弃）
            segments: 探槽段列表（已废弃，不再使用）
        """
        # 直接从投影表数据提取world_points
        self.world_points = []
        for row in projection_data:
            x = row.get('X', 0) or 0
            y = row.get('Y', 0) or 0
            self.world_points.append((x, y))
        print(f"[DXF load] world_points[0] = {self.world_points[0] if self.world_points else 'empty'}")
        # 确保起点是(0, 0)
        if self.world_points and (self.world_points[0][0] != 0 or self.world_points[0][1] != 0):
            self.world_points.insert(0, (0.0, 0.0))
            print(f"[DXF load] inserted (0,0) at beginning, new world_points[0] = {self.world_points[0]}")

        # 构建样品矩形列表（只包含样品区，跳过非采样区）
        self.sample_rects = []
        sample_idx = 0

        for i, row in enumerate(projection_data):
            sample_id = str(row.get('样号', '')).strip()

            # 获取当前行的X,Y作为终点
            x_end = row.get('X', 0) or 0
            y_end = row.get('Y', 0) or 0

            # 获取累计X/Y来计算起点
            sum_x = row.get('累计X', 0) or 0
            sum_y = row.get('累计Y', 0) or 0
            x_start = x_end - sum_x
            y_start = y_end - sum_y

            # 确定颜色（跳过非采样区，只处理样品区）
            if sample_id == '非采样区':
                continue  # 跳过非采样区
            elif sample_id.startswith('H'):
                color_index = sample_idx % 2
                sample_idx += 1
            else:
                continue

            self.sample_rects.append({
                'sample_id': sample_id,
                'x_start': x_start,
                'y_start': y_start,
                'x_end': x_end,
                'y_end': y_end,
                'color_index': color_index
            })

        # 计算总长度
        if self.world_points:
            total_length = abs(self.world_points[-1][0]) if self.world_points else 0.0
        else:
            total_length = 0.0

        # 设置trench_profile
        self.trench_profile = TrenchProfile(
            trench_id=trench_id,
            total_length=total_length,
            samples=[],  # 不再使用SampleArea结构
            start_x=0.0,
            start_y=0.0,
            segments=[]
        )

    def calculate_scale_factor(self) -> float:
        """计算比例尺因子

        Returns:
            图面距离与实际距离的比值
            公式: input_scale / output_scale
            例如 输入1:1000 -> 输出1:2000，则 scale_factor = 1000/2000 = 0.5
            即原来1个单位，输出时变为0.5个单位
        """
        return self.input_scale / self.scale

    def write_dxf_file(self, file_path: str):
        """写入DXF文件

        Args:
            file_path: 输出文件路径
        """
        print(f"[DXF Writer] write_dxf_file called, _final_coordinates={getattr(self, '_final_coordinates', False)}")
        if not self.trench_profile:
            raise ValueError("没有加载探槽数据")

        # 检查是否已经应用过整体移动，坐标是最终值
        final_coords = getattr(self, '_final_coordinates', False)
        print(f"[DXF write_dxf_file] _final_coordinates={final_coords}")
        if final_coords:
            # 坐标已经是最终值，跳过缩放
            scale_factor = 1.0
            print(f"[DXF] _final_coordinates=True, scale_factor=1.0 (跳过缩放)")
        else:
            scale_factor = self.calculate_scale_factor()
            print(f"[DXF] scale={self.scale}, scale_factor={scale_factor}")

        # 检查是否已经应用过整体移动
        # 如果是，则不再应用偏移（坐标已经移动过了）
        move_already_applied = getattr(self, '_move_applied', False)
        print(f"[DXF] world_points[0] = {self.world_points[0] if self.world_points else 'empty'}")
        print(f"[DXF] _move_applied = {move_already_applied}")

        if not move_already_applied:
            # 只有在没有应用过整体移动时，才应用偏移
            move_offset_x = getattr(self, 'move_offset_x', 0.0)
            move_offset_y = getattr(self, 'move_offset_y', 0.0)
            print(f"[DXF] applying move offset: ({move_offset_x}, {move_offset_y})")
            if move_offset_x != 0 or move_offset_y != 0:
                self.world_points = [(x + move_offset_x, y + move_offset_y) for x, y in self.world_points]
                for rect in self.sample_rects:
                    rect['x_start'] += move_offset_x
                    rect['y_start'] += move_offset_y
                    rect['x_end'] += move_offset_x
                    rect['y_end'] += move_offset_y

        with open(file_path, 'w', encoding='gb2312') as f:
            # 写入HEADER
            self._write_header(f)

            # 写入TABLES
            self._write_tables(f)

            # 写入ENTITIES
            self._write_entities(f, scale_factor)

            # 写入EOF
            f.write("  0\n")
            f.write("EOF\n")

    def _write_header(self, f):
        """写HEADER段"""
        f.write("  0\n")
        f.write("SECTION\n")
        f.write("  2\n")
        f.write("HEADER\n")

        # ACAD版本
        f.write("  9\n")
        f.write("$ACADVER\n")
        f.write("  1\n")
        f.write("AC1009\n")

        # 文字编码
        f.write("  9\n")
        f.write("$DWGCODEPAGE\n")
        f.write("  3\n")
        f.write("GB2312\n")

        # 单位
        f.write("  9\n")
        f.write("$INSUNITS\n")
        f.write(" 70\n")
        f.write("4\n")

        f.write("  0\n")
        f.write("ENDSEC\n")

    def _write_tables(self, f):
        """写TABLES段"""
        f.write("  0\n")
        f.write("SECTION\n")
        f.write("  2\n")
        f.write("TABLES\n")

        # LAYER表
        f.write("  0\n")
        f.write("TABLE\n")
        f.write("  2\n")
        f.write("LAYER\n")
        f.write(" 70\n")
        f.write("6\n")  # 图层数量+1

        # 图层1: TRENCH - 探槽线
        self._write_layer(f, "TRENCH", 1)

        # 图层2: SAMPLE - 样品边框
        self._write_layer(f, "SAMPLE", 7)

        # 图层3: SAMPLE_FILL - 样品填充
        self._write_layer(f, "SAMPLE_FILL", 7)

        # 图层4: TEXT - 标注
        self._write_layer(f, "TEXT", 3)

        # 图层5: MARKER - 起点标记
        self._write_layer(f, "MARKER", 5)

        # 图层6: WALL - 探槽壁轮廓
        self._write_layer(f, "WALL", 6)

        f.write("  0\n")
        f.write("ENDTAB\n")
        f.write("  0\n")
        f.write("ENDSEC\n")

    def _write_layer(self, f, name: str, color: int):
        """写单个图层定义"""
        f.write("  0\n")
        f.write("LAYER\n")
        f.write("  2\n")
        f.write(f"{name}\n")
        f.write(" 70\n")
        f.write("0\n")
        f.write(" 62\n")
        f.write(f"{color}\n")
        f.write("  6\n")
        f.write("CONTINUOUS\n")

    def _write_entities(self, f, scale_factor: float):
        """写ENTITIES段"""
        f.write("  0\n")
        f.write("SECTION\n")
        f.write("  2\n")
        f.write("ENTITIES\n")

        profile = self.trench_profile
        is_final = getattr(self, '_final_coordinates', False)
        print(f"[DXF _write_entities] is_final={is_final}, _boundary_perps has={hasattr(self, '_boundary_perps')}, len={len(getattr(self, '_boundary_perps', {}))}")
        print(f"[DXF _write_entities] world_points len={len(self.world_points)}, sample_rects len={len(self.sample_rects)}")

        # 当is_final=True时，直接使用Preview传来的数据，不再重新计算
        if is_final:
            # === 直接使用Preview数据模式 ===
            print("[DXF] is_final=True，使用Preview直接传来的数据")

            # 0. 如果boundary_perps已从Preview传来，直接使用；否则预计算
            if not hasattr(self, '_boundary_perps') or not self._boundary_perps:
                self._precalculate_boundary_perps_final()
            else:
                print(f"[DXF] 使用Preview传来的boundary_perps: {len(self._boundary_perps)} 个")
                print(f"[DXF] boundary_perps keys: {sorted(self._boundary_perps.keys())}")

            # 调试：打印前几个样品的索引信息
            for i, rect in enumerate(self.sample_rects[:10]):
                if isinstance(rect, dict):
                    sid = rect.get('sample_id', '?')
                    s_idx = rect.get('start_idx', -1)
                    e_idx = rect.get('end_idx', -1)
                else:
                    sid = getattr(rect, 'sample_id', '?')
                    s_idx = getattr(rect, 'start_idx', -1)
                    e_idx = getattr(rect, 'end_idx', -1)
                s_in = s_idx in self._boundary_perps if hasattr(self, '_boundary_perps') else False
                e_in = e_idx in self._boundary_perps if hasattr(self, '_boundary_perps') else False
                print(f"[DXF] 样品{i} {sid}: start_idx={s_idx}(in_perps={s_in}), end_idx={e_idx}(in_perps={e_in})")

            # 1. 绘制探槽主线（AB线）- 使用POLYLINE多段线
            # world_points已经是图面坐标，XY交换: (Y,X) -> (x,y)
            ab_points = [(p[1], p[0]) for p in self.world_points]
            self._write_polyline(f, ab_points, "TRENCH", 1)

            # 2. 绘制探槽壁（CD线和AC、BD线）
            if self.show_walls and hasattr(self, 'cd_points') and self.cd_points:
                # CD线 - 使用POLYLINE多段线
                cd_points_xy = [(p[1], p[0]) for p in self.cd_points]
                self._write_polyline(f, cd_points_xy, "WALL", 6)
                # AC线（AB起点到CD起点）
                if self.world_points and self.cd_points:
                    ab_start = self.world_points[0]
                    cd_start = self.cd_points[0]
                    self._write_single_line(f, ab_start[1], ab_start[0], cd_start[1], cd_start[0], "WALL", 6)
                    # BD线（AB终点到CD终点）
                    ab_end = self.world_points[-1]
                    cd_end = self.cd_points[-1]
                    self._write_single_line(f, ab_end[1], ab_end[0], cd_end[1], cd_end[0], "WALL", 6)

            # 3. 绘制样品矩形（将投影坐标转换为图面坐标后绘制）
            for rect in self.sample_rects:
                # rect格式: x_start, y_start, x_end, y_end 是(X_投影, Y_投影)格式
                # Preview中: X_图 = X_投影 * scale_factor, Y_图 = Y_投影 * scale_factor
                scale = getattr(self, '_export_scale_factor', 1.0)

                # 获取边界点索引（兼容dict和SampleRect对象）
                if isinstance(rect, dict):
                    start_idx = rect.get('start_idx', -1)
                    end_idx = rect.get('end_idx', -1)
                    x_start = rect.get('x_start', 0)
                    y_start = rect.get('y_start', 0)
                    x_end = rect.get('x_end', 0)
                    y_end = rect.get('y_end', 0)
                    sample_id = rect.get('sample_id', '?')
                    color_index = rect.get('color_index', 0)
                else:
                    start_idx = getattr(rect, 'start_idx', -1)
                    end_idx = getattr(rect, 'end_idx', -1)
                    x_start = getattr(rect, 'x_start', 0)
                    y_start = getattr(rect, 'y_start', 0)
                    x_end = getattr(rect, 'x_end', 0)
                    y_end = getattr(rect, 'y_end', 0)
                    sample_id = getattr(rect, 'sample_id', '?')
                    color_index = getattr(rect, 'color_index', 0)

                # 跳过非采样区，只显示样品区
                if sample_id == '非采样区':
                    continue

                # 起点（图面坐标）
                x1_proj = x_start
                y1_proj = y_start
                x1_fig = x1_proj * scale  # X_图
                y1_fig = y1_proj * scale  # Y_图

                # 终点（图面坐标）
                x4_proj = x_end
                y4_proj = y_end
                x4_fig = x4_proj * scale
                y4_fig = y4_proj * scale

                # 厚度偏移计算 - 使用共用边界垂线
                offset = self.sample_thickness * scale

                # 起点边的法向量（使用共用的boundary_perps）
                if start_idx >= 0 and hasattr(self, '_boundary_perps') and start_idx in self._boundary_perps:
                    perp_x1, perp_y1 = self._boundary_perps[start_idx]
                    print(f"[DXF] 样品 {sample_id}: 使用boundary_perps start_idx={start_idx}")
                else:
                    # 回退：计算当前样品的切线方向
                    dx = x4_fig - x1_fig
                    dy = y4_fig - y1_fig
                    seg_len = math.sqrt(dx*dx + dy*dy)
                    if seg_len > 0.001:
                        dx /= seg_len
                        dy /= seg_len
                    else:
                        dx, dy = 1.0, 0.0
                    perp_x1 = -dy * self.sample_side
                    perp_y1 = dx * self.sample_side
                    print(f"[DXF] 样品 {sample_id}: 回退计算 start_idx={start_idx}, boundary_perps={hasattr(self, '_boundary_perps')}")

                # 终点边的法向量（使用共用的boundary_perps）
                if end_idx >= 0 and hasattr(self, '_boundary_perps') and end_idx in self._boundary_perps:
                    perp_x4, perp_y4 = self._boundary_perps[end_idx]
                else:
                    dx = x4_fig - x1_fig
                    dy = y4_fig - y1_fig
                    seg_len = math.sqrt(dx*dx + dy*dy)
                    if seg_len > 0.001:
                        dx /= seg_len
                        dy /= seg_len
                    else:
                        dx, dy = 1.0, 0.0
                    perp_x4 = -dy * self.sample_side
                    perp_y4 = dx * self.sample_side

                # 计算四个角点
                x2_fig = x1_fig + perp_x1 * offset
                y2_fig = y1_fig + perp_y1 * offset
                x3_fig = x4_fig + perp_x4 * offset
                y3_fig = y4_fig + perp_y4 * offset

                # 颜色：0=白色, 1=黑色, 2=灰色(非采样区), 3=橙色
                if color_index == 0:
                    color = 8   # 白色
                elif color_index == 1:
                    color = 7   # 黑色
                elif color_index == 2:
                    color = 9   # 灰色（非采样区）
                elif color_index == 3:
                    color = 30  # 橙色
                else:
                    color = 9   # 默认灰色

                # 绘制4条边（写入DXF时XY交换）
                # DXF坐标: x = Y_图, y = X_图
                self._write_single_line(f, y1_fig, x1_fig, y2_fig, x2_fig, "SAMPLE", color)
                self._write_single_line(f, y2_fig, x2_fig, y3_fig, x3_fig, "SAMPLE", color)
                self._write_single_line(f, y3_fig, x3_fig, y4_fig, x4_fig, "SAMPLE", color)
                self._write_single_line(f, y4_fig, x4_fig, y1_fig, x1_fig, "SAMPLE", color)

                # 绘制SOLID填充实体（仅采样区，非采样区不填充）
                if sample_id != '非采样区':
                    # DXF坐标：x = Y_图, y = X_图
                    f.write("  0\n")
                    f.write("SOLID\n")
                    f.write("100\n")
                    f.write("AcDbEntity\n")
                    f.write("  8\n")
                    f.write("SAMPLE_FILL\n")
                    f.write(" 62\n")
                    f.write(f"{color}\n")
                    f.write("100\n")
                    f.write("AcDbTrace\n")
                    # 四个角点（DXF坐标XY交换）
                    f.write(" 10\n")
                    f.write(f"{y1_fig:.6f}\n")
                    f.write(" 20\n")
                    f.write(f"{x1_fig:.6f}\n")
                    f.write(" 30\n")
                    f.write("0.0\n")
                    f.write(" 11\n")
                    f.write(f"{y2_fig:.6f}\n")
                    f.write(" 21\n")
                    f.write(f"{x2_fig:.6f}\n")
                    f.write(" 31\n")
                    f.write("0.0\n")
                    f.write(" 12\n")
                    f.write(f"{y4_fig:.6f}\n")
                    f.write(" 22\n")
                    f.write(f"{x4_fig:.6f}\n")
                    f.write(" 32\n")
                    f.write("0.0\n")
                    f.write(" 13\n")
                    f.write(f"{y3_fig:.6f}\n")
                    f.write(" 23\n")
                    f.write(f"{x3_fig:.6f}\n")
                    f.write(" 33\n")
                    f.write("0.0\n")

                # 绘制样品号标注
                if self.show_labels and sample_id != '非采样区':
                    # 计算标注位置：矩形中点向样品侧偏移
                    mid_x_fig = (x1_fig + x4_fig) / 2
                    mid_y_fig = (y1_fig + y4_fig) / 2
                    # 使用起点和终点的平均法向量方向
                    avg_perp_x = (perp_x1 + perp_x4) / 2
                    avg_perp_y = (perp_y1 + perp_y4) / 2
                    # 标注位置偏移：向样品侧偏移1.5倍厚度
                    label_offset = offset * 1.5
                    label_x = mid_x_fig + avg_perp_x * label_offset
                    label_y = mid_y_fig + avg_perp_y * label_offset
                    # DXF坐标：XY交换
                    dxf_x = label_y
                    dxf_y = label_x
                    # 写入TEXT实体（水平方向）
                    f.write("  0\n")
                    f.write("TEXT\n")
                    f.write("  8\n")
                    f.write("TEXT\n")
                    f.write(" 62\n")
                    f.write("3\n")  # 黄色
                    f.write(" 10\n")
                    f.write(f"{dxf_x:.6f}\n")
                    f.write(" 20\n")
                    f.write(f"{dxf_y:.6f}\n")
                    f.write(" 30\n")
                    f.write("0.0\n")
                    f.write(" 40\n")
                    f.write("1.0\n")  # 文字高度
                    f.write(" 72\n")
                    f.write("1\n")  # 居中对齐
                    f.write(" 73\n")
                    f.write("2\n")  # 垂直居中
                    f.write(" 11\n")
                    f.write(f"{dxf_x:.6f}\n")
                    f.write(" 21\n")
                    f.write(f"{dxf_y:.6f}\n")
                    f.write(" 31\n")
                    f.write("0.0\n")
                    f.write("  1\n")
                    f.write(f"{sample_id}\n")

            # 4. 绘制起点标记
            if self.world_points:
                start_x = self.world_points[0][1]
                start_y = self.world_points[0][0]
                # 绘制十字叉
                self._write_single_line(f, start_x - 5, start_y, start_x + 5, start_y, "TEXT", 3)
                self._write_single_line(f, start_x, start_y - 5, start_x, start_y + 5, "TEXT", 3)
        else:
            # === 原始模式：从投影数据重新计算 ===
            # 0. 预计算共用边界垂线
            self._precalculate_boundary_perps(scale_factor)

            # 1. 绘制探槽壁轮廓
            if self.show_walls:
                self._write_trench_walls(f, profile, scale_factor)

            # 2. 绘制探槽主线
            self._write_trench_line(f, profile, scale_factor)

            # 3. 绘制样品区域
            for rect in self.sample_rects:
                self._write_rect_by_coords(f, rect, scale_factor)

            # 4. 绘制起点标记
            self._write_start_marker(f, profile, scale_factor)

            # 5. 绘制样品号标注
            if self.show_labels:
                for rect in self.sample_rects:
                    self._write_rect_label(f, rect, scale_factor)

        f.write("  0\n")
        f.write("ENDSEC\n")

    def _precalculate_boundary_perps(self, scale_factor: float):
        """预计算所有样品边界点的共用垂线方向

        这确保相邻样品在边界处使用相同的垂线方向，避免因段方向突变导致的样品区重叠

        坐标系统：world_points 是 (X_投影, Y_投影)
        图面坐标：(x_图, y_图) = (Y_投影, X_投影)
        """
        self._boundary_perps = {}  # (rect_idx, is_start) -> (perp_x, perp_y)

        if not self.sample_rects or not self.world_points:
            return

        # 收集所有样品边界点索引
        boundary_map = {}  # rect_idx -> (start_idx, end_idx)
        for rect_idx, rect in enumerate(self.sample_rects):
            # 兼容dict和object格式的rect
            if isinstance(rect, dict):
                start_idx = rect.get('start_idx', -1)
                end_idx = rect.get('end_idx', -1)
                x_start = rect.get('x_start', 0)
                y_start = rect.get('y_start', 0)
                x_end = rect.get('x_end', 0)
                y_end = rect.get('y_end', 0)
            else:
                start_idx = getattr(rect, 'start_idx', -1)
                end_idx = getattr(rect, 'end_idx', -1)
                x_start = getattr(rect, 'x_start', 0)
                y_start = getattr(rect, 'y_start', 0)
                x_end = getattr(rect, 'x_end', 0)
                y_end = getattr(rect, 'y_end', 0)

            if start_idx < 0 or end_idx < 0:
                # 尝试通过坐标匹配找到索引
                # world_points格式是(Y, X)，所以key应该是(y, x)
                start_key = (round(y_start, 3), round(x_start, 3))
                end_key = (round(y_end, 3), round(x_end, 3))
                for idx, wp in enumerate(self.world_points):
                    wp_key = (round(wp[0], 3), round(wp[1], 3))
                    if wp_key == start_key:
                        start_idx = idx
                    if wp_key == end_key:
                        end_idx = idx
            boundary_map[rect_idx] = (start_idx, end_idx)

        # 为每个唯一边界索引计算垂线方向
        unique_indices = set()
        for start_idx, end_idx in boundary_map.values():
            if start_idx >= 0:
                unique_indices.add(start_idx)
            if end_idx >= 0:
                unique_indices.add(end_idx)

        for idx in unique_indices:
            if idx >= len(self.world_points):
                continue

            p = self.world_points[idx]

            # 计算该点处的切线方向
            if idx == 0:
                next_p = self.world_points[idx + 1]
                dx = next_p[0] - p[0]  # X_投影差
                dy = next_p[1] - p[1]  # Y_投影差
            elif idx == len(self.world_points) - 1:
                prev_p = self.world_points[idx - 1]
                dx = p[0] - prev_p[0]
                dy = p[1] - prev_p[1]
            else:
                prev_p = self.world_points[idx - 1]
                next_p = self.world_points[idx + 1]
                dx = next_p[0] - prev_p[0]
                dy = next_p[1] - prev_p[1]

            seg_len = math.sqrt(dx * dx + dy * dy)
            if seg_len < 0.001:
                continue

            # 归一化切线
            dx /= seg_len
            dy /= seg_len

            # 垂线方向：world_points 是 (X_投影, Y_投影)
            # 切线方向 (dx, dy) = (dX, dY)
            # 左手边法向量 = (-dY, dX) = (-dy, dx)
            # 然后根据sample_side调整方向
            perp_x = -dy * self.sample_side
            perp_y = dx * self.sample_side
            perp_len = math.sqrt(perp_x * perp_x + perp_y * perp_y)
            if perp_len > 0.001:
                perp_x /= perp_len
                perp_y /= perp_len
                self._boundary_perps[idx] = (perp_x, perp_y)

    def _precalculate_boundary_perps_final(self):
        """预计算共用边界垂线（用于is_final=True模式）

        当is_final=True时，world_points已经是图面坐标(Y_图, X_图)
        垂线计算直接在图面坐标中进行
        """
        self._boundary_perps = {}  # idx -> (perp_x, perp_y)

        if not self.sample_rects or not self.world_points:
            return

        print(f"[DXF _precalculate_boundary_perps_final] world_points={len(self.world_points)} points, sample_rects={len(self.sample_rects)}")

        # 收集所有样品边界点索引
        boundary_map = {}  # rect_idx -> (start_idx, end_idx)
        for rect_idx, rect in enumerate(self.sample_rects):
            # 兼容dict和object格式的rect
            if isinstance(rect, dict):
                start_idx = rect.get('start_idx', -1)
                end_idx = rect.get('end_idx', -1)
            else:
                start_idx = getattr(rect, 'start_idx', -1)
                end_idx = getattr(rect, 'end_idx', -1)
            boundary_map[rect_idx] = (start_idx, end_idx)

        # 打印相邻样品的边界索引，检查是否共享
        for rect_idx in range(len(self.sample_rects) - 1):
            start1, end1 = boundary_map[rect_idx]
            start2, end2 = boundary_map[rect_idx + 1]
            sample_id1 = self.sample_rects[rect_idx].get('sample_id', '?') if isinstance(self.sample_rects[rect_idx], dict) else self.sample_rects[rect_idx].sample_id
            sample_id2 = self.sample_rects[rect_idx + 1].get('sample_id', '?') if isinstance(self.sample_rects[rect_idx + 1], dict) else self.sample_rects[rect_idx + 1].sample_id
            print(f"[DXF] 相邻样品 {sample_id1}(idx={start1}~{end1}) 和 {sample_id2}(idx={start2}~{end2}), 是否共享边界: end1={end1} == start2={start2}")

        # 为每个唯一边界索引计算垂线方向
        unique_indices = set()
        for start_idx, end_idx in boundary_map.values():
            if start_idx >= 0:
                unique_indices.add(start_idx)
            if end_idx >= 0:
                unique_indices.add(end_idx)

        print(f"[DXF _precalculate_boundary_perps_final] unique boundary indices: {len(unique_indices)}, indices={sorted(unique_indices)[:10]}...")

        for idx in unique_indices:
            if idx >= len(self.world_points):
                continue

            p = self.world_points[idx]

            # 计算该点处的切线方向（图面坐标）
            if idx == 0:
                next_p = self.world_points[idx + 1]
                dx = next_p[0] - p[0]  # Y_图差
                dy = next_p[1] - p[1]  # X_图差
            elif idx == len(self.world_points) - 1:
                prev_p = self.world_points[idx - 1]
                dx = p[0] - prev_p[0]
                dy = p[1] - prev_p[1]
            else:
                prev_p = self.world_points[idx - 1]
                next_p = self.world_points[idx + 1]
                dx = next_p[0] - prev_p[0]
                dy = next_p[1] - prev_p[1]

            seg_len = math.sqrt(dx * dx + dy * dy)
            if seg_len < 0.001:
                continue

            # 归一化切线
            dx /= seg_len
            dy /= seg_len

            # 垂线方向（图面坐标）
            # 切线(dx, dy)沿着探槽方向（从Y_图到X_图）
            # 左手边法向量 = (-dy, dx)
            perp_x = -dy * self.sample_side
            perp_y = dx * self.sample_side
            perp_len = math.sqrt(perp_x * perp_x + perp_y * perp_y)
            if perp_len > 0.001:
                perp_x /= perp_len
                perp_y /= perp_len
                self._boundary_perps[idx] = (perp_x, perp_y)

        print(f"[DXF _precalculate_boundary_perps_final] calculated {len(self._boundary_perps)} boundary perps")

    def _write_trench_walls(self, f, profile: TrenchProfile, scale_factor: float):
        """绘制探槽壁轮廓（4条线）

        探槽结构：
            D -------- C (另一壁，与样品同侧)
            |          |
            |  偏移距离 |
            |          |
            A -------- B (探槽主轴线)

        AB = 探槽主轴线
        CD = AB的等距平行线（每一段都垂直偏移wall_offset距离）
        AC = 槽头（垂直连接A和D）
        BD = 槽尾（垂直连接B和C）

        偏移方向：与sample_side关联
        - sample_side=-1(左侧)时，偏移方向为向左
        - sample_side=+1(右侧)时，偏移方向为向右

        坐标系统与预览一致，使用XY交换 (x_图, y_图) = (Y_投影, X_投影)

        算法：按点处理，使用共用边界垂线避免样品区重叠
        """
        if not self.world_points or len(self.world_points) < 2:
            return

        # 调试日志
        print(f"[DXF _write_trench_walls] world_points[0]={self.world_points[0]}, world_points[-1]={self.world_points[-1]}")
        print(f"[DXF _write_trench_walls] sample_side={self.sample_side}, wall_offset={self.wall_offset}")
        print(f"[DXF _write_trench_walls] _final_coordinates={getattr(self, '_final_coordinates', False)}")
        print(f"[DXF _write_trench_walls] _boundary_perps count={len(getattr(self, '_boundary_perps', {}))}")
        print(f"[DXF _write_trench_walls] cd_points={len(getattr(self, 'cd_points', []))} points")

        # 绘制探槽壁图层
        wall_layer = "WALL"
        wall_color = 6  # 洋红色

        n = len(self.world_points)

        # 直接基于AB计算CD（垂直平行线）
        # AB在DXF中的坐标是XY交换后的，所以CD也要XY交换
        is_final = getattr(self, '_final_coordinates', False)
        cd_points = []
        for i, p_proj in enumerate(self.world_points):
            # 计算当前点的DXF坐标（XY交换）
            if is_final:
                p_x = p_proj[1]  # Y_投影 -> DXF x
                p_y = p_proj[0]  # X_投影 -> DXF y
            else:
                p_x = self.start_x + p_proj[1] * scale_factor
                p_y = self.start_y + p_proj[0] * scale_factor

            # 计算切线方向
            if i == 0:
                next_proj = self.world_points[i + 1]
                if is_final:
                    dx = next_proj[1] - p_proj[1]
                    dy = next_proj[0] - p_proj[0]
                else:
                    dx = (self.start_x + next_proj[1] * scale_factor) - p_x
                    dy = (self.start_y + next_proj[0] * scale_factor) - p_y
            elif i == n - 1:
                prev_proj = self.world_points[i - 1]
                if is_final:
                    dx = p_proj[1] - prev_proj[1]
                    dy = p_proj[0] - prev_proj[0]
                else:
                    dx = p_x - (self.start_x + prev_proj[1] * scale_factor)
                    dy = p_y - (self.start_y + prev_proj[0] * scale_factor)
            else:
                prev_proj = self.world_points[i - 1]
                next_proj = self.world_points[i + 1]
                if is_final:
                    dx = next_proj[1] - prev_proj[1]
                    dy = next_proj[0] - prev_proj[0]
                else:
                    dx = (self.start_x + next_proj[1] * scale_factor) - (self.start_x + prev_proj[1] * scale_factor)
                    dy = (self.start_y + next_proj[0] * scale_factor) - (self.start_y + prev_proj[0] * scale_factor)

            seg_len = math.sqrt(dx * dx + dy * dy)
            if seg_len < 0.001:
                if i > 0:
                    prev_proj = self.world_points[i - 1]
                    if is_final:
                        dx = p_proj[1] - prev_proj[1]
                        dy = p_proj[0] - prev_proj[0]
                    else:
                        dx = p_x - (self.start_x + prev_proj[1] * scale_factor)
                        dy = p_y - (self.start_y + prev_proj[0] * scale_factor)
                    seg_len = math.sqrt(dx * dx + dy * dy)

            if seg_len < 0.001:
                continue

            # 归一化切线
            dx /= seg_len
            dy /= seg_len

            # 法向量（左手边）
            perp_x = -dy * self.sample_side
            perp_y = dx * self.sample_side

            # 计算CD线上的点
            offset_x = p_x + self.wall_offset * perp_x
            offset_y = p_y + self.wall_offset * perp_y
            cd_points.append((offset_x, offset_y))

        if len(cd_points) < 2:
            return

        # 获取AB的起点和终点坐标（DXF坐标，XY交换后）
        if is_final:
            A_x = self.world_points[0][1]
            A_y = self.world_points[0][0]
            B_x = self.world_points[-1][1]
            B_y = self.world_points[-1][0]
        else:
            A_x = self.start_x + self.world_points[0][1] * scale_factor
            A_y = self.start_y + self.world_points[0][0] * scale_factor
            B_x = self.start_x + self.world_points[-1][1] * scale_factor
            B_y = self.start_y + self.world_points[-1][0] * scale_factor

        # 获取CD的起点和终点坐标
        D_x, D_y = cd_points[0]
        C_x, C_y = cd_points[-1]

        # 绘制CD - 使用POLYLINE多段线
        self._write_polyline(f, cd_points, wall_layer, wall_color)

        # 绘制AC和BD
        self._write_single_line(f, A_x, A_y, D_x, D_y, wall_layer, wall_color)
        self._write_single_line(f, B_x, B_y, C_x, C_y, wall_layer, wall_color)

    def _write_trench_line(self, f, profile: TrenchProfile, scale_factor: float):
        """绘制探槽主线（POLYLINE多段线）

        坐标系统与预览一致，使用XY交换 (x_图, y_图) = (Y_投影, X_投影)
        """
        if not self.world_points or len(self.world_points) < 2:
            # 如果没有世界坐标点，绘制水平线作为后备
            start_x = profile.start_x
            end_x = profile.start_x + profile.total_length * scale_factor
            y = profile.start_y
            self._write_single_line(f, start_x, y, end_x, y, "TRENCH", 1)
        else:
            # 检查坐标是否已经是最终格式（图面坐标）
            is_final = getattr(self, '_final_coordinates', False)
            if is_final:
                # world_points是(X_投影, Y_投影)，DXF需要XY交换，使用POLYLINE
                ab_points = [(p[1], p[0]) for p in self.world_points]
                self._write_polyline(f, ab_points, "TRENCH", 1)
            else:
                # world_points是(X_投影, Y_投影)格式，需要交换，使用POLYLINE
                ab_points = [(profile.start_x + p[1] * scale_factor,
                             profile.start_y + p[0] * scale_factor) for p in self.world_points]
                self._write_polyline(f, ab_points, "TRENCH", 1)

    def _write_single_line(self, f, x1: float, y1: float, x2: float, y2: float,
                           layer: str, color: int):
        """绘制单条线段"""
        f.write("  0\n")
        f.write("LINE\n")
        f.write("  8\n")
        f.write(f"{layer}\n")
        f.write(" 62\n")
        f.write(f"{color}\n")
        f.write("  10\n")
        f.write(f"{x1:.6f}\n")
        f.write("  20\n")
        f.write(f"{y1:.6f}\n")
        f.write("  30\n")
        f.write("0.0\n")
        f.write("  11\n")
        f.write(f"{x2:.6f}\n")
        f.write("  21\n")
        f.write(f"{y2:.6f}\n")
        f.write("  31\n")
        f.write("0.0\n")

    def _write_polyline(self, f, points: List[Tuple[float, float]], layer: str, color: int):
        """绘制多段线（POLYLINE）

        参数:
            f: 文件对象
            points: 点列表 [(x, y), ...]
            layer: 图层名称
            color: 颜色编号
        """
        if len(points) < 2:
            return

        # POLYLINE 头
        f.write("  0\n")
        f.write("POLYLINE\n")
        f.write("  8\n")
        f.write(f"{layer}\n")
        f.write(" 66\n")
        f.write("1\n")  # 顶点跟随
        f.write(" 70\n")
        f.write("0\n")  # 不是封闭多段线
        f.write(" 30\n")
        f.write("0.0\n")

        # 写入所有顶点
        for x, y in points:
            f.write("  0\n")
            f.write("VERTEX\n")
            f.write("  8\n")
            f.write(f"{layer}\n")
            f.write(" 10\n")
            f.write(f"{x:.6f}\n")
            f.write(" 20\n")
            f.write(f"{y:.6f}\n")
            f.write(" 30\n")
            f.write("0.0\n")

        # POLYLINE 结束
        f.write("  0\n")
        f.write("SEQEND\n")
        f.write("  8\n")
        f.write(f"{layer}\n")

    def _write_rect_by_coords(self, f, rect: Dict, scale_factor: float):
        """使用世界坐标绘制样品矩形区域

        坐标系统与预览一致，使用XY交换 (x_图, y_图) = (Y_投影, X_投影)

        rect包含: x_start, y_start, x_end, y_end, sample_id, color_index

        改进：使用预计算的共用边界垂线，避免相邻样品边界不重合
        """
        import math

        # 检查是否是最终坐标
        is_final = getattr(self, '_final_coordinates', False)

        # 坐标处理：取决于坐标是否已经是最终格式
        if is_final:
            # rect已经是(Y_投影, X_投影)格式，直接使用
            x1 = rect['y_start']  # Y_投影 -> DXF x
            y1 = rect['x_start']  # X_投影 -> DXF y
            x4 = rect['y_end']
            y4 = rect['x_end']
        else:
            # rect是(X_投影, Y_投影)格式，需要XY交换和缩放
            x1 = rect['y_start'] * scale_factor  # Y_投影 -> x_图
            y1 = rect['x_start'] * scale_factor  # X_投影 -> y_图
            x4 = rect['y_end'] * scale_factor    # Y_投影 -> x_图
            y4 = rect['x_end'] * scale_factor    # X_投影 -> y_图

        # 找到当前矩形在sample_rects中的索引
        idx = self.sample_rects.index(rect)

        # 获取边界点索引（兼容dict和object格式）
        if isinstance(rect, dict):
            start_idx = rect.get('start_idx', -1)
            end_idx = rect.get('end_idx', -1)
        else:
            start_idx = getattr(rect, 'start_idx', -1)
            end_idx = getattr(rect, 'end_idx', -1)

        # 如果没有索引，尝试通过坐标匹配找到
        # world_points格式是(Y, X)，所以key应该是(y, x)
        if start_idx < 0 or end_idx < 0:
            start_key = (round(rect['y_start'], 3), round(rect['x_start'], 3))
            end_key = (round(rect['y_end'], 3), round(rect['x_end'], 3))
            for i, wp in enumerate(self.world_points):
                wp_key = (round(wp[0], 3), round(wp[1], 3))
                if wp_key == start_key:
                    start_idx = i
                if wp_key == end_key:
                    end_idx = i

        # 确定使用哪个垂线方向
        # 对于起点(p1, p2边)，使用start_idx处的垂线
        # 对于终点(p4, p3边)，使用end_idx处的垂线
        perp_x_start, perp_y_start = None, None
        perp_x_end, perp_y_end = None, None

        if hasattr(self, '_boundary_perps') and self._boundary_perps:
            if start_idx >= 0 and start_idx in self._boundary_perps:
                perp_x_start, perp_y_start = self._boundary_perps[start_idx]
            if end_idx >= 0 and end_idx in self._boundary_perps:
                perp_x_end, perp_y_end = self._boundary_perps[end_idx]

        # 如果没有预计算的垂线，回退到原始计算方法
        if perp_x_start is None or perp_x_end is None:
            # 使用相邻样品的端点计算切线方向
            if idx < len(self.sample_rects) - 1:
                next_rect = self.sample_rects[idx + 1]
                trench_dx = next_rect['y_end'] * scale_factor - x4
                trench_dy = next_rect['x_end'] * scale_factor - y4
            elif idx > 0:
                prev_rect = self.sample_rects[idx - 1]
                trench_dx = x4 - prev_rect['y_end'] * scale_factor
                trench_dy = y4 - prev_rect['x_end'] * scale_factor
            else:
                trench_dx = x4 - x1
                trench_dy = y4 - y1

            # 归一化方向向量
            trench_len = math.sqrt(trench_dx * trench_dx + trench_dy * trench_dy)
            if trench_len < 0.001:
                trench_dx, trench_dy = 1.0, 0.0
                trench_len = 1.0
            trench_dx /= trench_len
            trench_dy /= trench_len

            # 计算垂直方向（法线方向 = (-dy, dx)）
            perp_x = -trench_dy
            perp_y = trench_dx
            perp_x_start = perp_x
            perp_y_start = perp_y
            perp_x_end = perp_x
            perp_y_end = perp_y

        # 根据sample_side确定厚度偏移方向
        # offset_magnitude 需要根据原始 scale_factor 缩放
        if getattr(self, '_final_coordinates', False):
            offset_scale = self.input_scale / self.scale
        else:
            offset_scale = scale_factor
        offset_magnitude = self.sample_thickness * offset_scale

        # 计算四个角点世界坐标
        # 起点边(p1->p2)使用perp_start
        x2 = x1 + perp_x_start * offset_magnitude
        y2 = y1 + perp_y_start * offset_magnitude
        # 终点边(p4->p3)使用perp_end
        x3 = x4 + perp_x_end * offset_magnitude
        y3 = y4 + perp_y_end * offset_magnitude

        # 颜色映射：黑色=7，白色=8，灰色=9，橙色=30
        color_index = rect['color_index']
        if color_index == 0:
            color = 8   # 白色
        elif color_index == 1:
            color = 7  # 黑色
        elif color_index == 3:
            color = 30  # 橙色
        else:
            color = 9  # 灰色

        # 顺序：p1→p2→p3→p4→p1（闭合）
        polygon = [
            (x1, y1),
            (x2, y2),
            (x3, y3),
            (x4, y4),
        ]

        # 1. 绘制4条边（LINE实体）
        for i in range(4):
            pt1 = polygon[i]
            pt2 = polygon[(i + 1) % 4]

            f.write("  0\n")
            f.write("LINE\n")
            f.write("  8\n")
            f.write("SAMPLE\n")
            f.write("  62\n")
            f.write(f"{color}\n")

            f.write("  10\n")
            f.write(f"{pt1[0]:.6f}\n")
            f.write("  20\n")
            f.write(f"{pt1[1]:.6f}\n")
            f.write("  30\n")
            f.write("0.0\n")

            f.write("  11\n")
            f.write(f"{pt2[0]:.6f}\n")
            f.write("  21\n")
            f.write(f"{pt2[1]:.6f}\n")
            f.write("  31\n")
            f.write("0.0\n")

        # 2. 绘制SOLID实体（实体填充）
        f.write("  0\n")
        f.write("SOLID\n")
        f.write("100\n")
        f.write("AcDbEntity\n")
        f.write("  8\n")
        f.write("SAMPLE_FILL\n")
        f.write(" 62\n")
        f.write(f"{color}\n")
        f.write("100\n")
        f.write("AcDbTrace\n")
        # 四个角点
        f.write(" 10\n")
        f.write(f"{polygon[0][0]:.6f}\n")
        f.write(" 20\n")
        f.write(f"{polygon[0][1]:.6f}\n")
        f.write(" 30\n")
        f.write("0.0\n")
        f.write(" 11\n")
        f.write(f"{polygon[1][0]:.6f}\n")
        f.write(" 21\n")
        f.write(f"{polygon[1][1]:.6f}\n")
        f.write(" 31\n")
        f.write("0.0\n")
        f.write(" 12\n")
        f.write(f"{polygon[3][0]:.6f}\n")
        f.write(" 22\n")
        f.write(f"{polygon[3][1]:.6f}\n")
        f.write(" 32\n")
        f.write("0.0\n")
        f.write(" 13\n")
        f.write(f"{polygon[2][0]:.6f}\n")
        f.write(" 23\n")
        f.write(f"{polygon[2][1]:.6f}\n")
        f.write(" 33\n")
        f.write("0.0\n")

    def _write_rect_label(self, f, rect: Dict, scale_factor: float):
        """绘制样品号标注

        坐标系统与预览一致，使用XY交换 (x_图, y_图) = (Y_投影, X_投影)
        """
        import math

        # 做XY交换和缩放
        x1 = rect['y_start'] * scale_factor  # Y_投影 -> x_图
        y1 = rect['x_start'] * scale_factor  # X_投影 -> y_图
        x4 = rect['y_end'] * scale_factor    # Y_投影 -> x_图
        y4 = rect['x_end'] * scale_factor    # X_投影 -> y_图

        # 找到当前矩形在sample_rects中的索引
        idx = self.sample_rects.index(rect)

        # 使用相邻样品的端点计算切线方向
        if idx < len(self.sample_rects) - 1:
            next_rect = self.sample_rects[idx + 1]
            trench_dx = next_rect['y_end'] * scale_factor - x4
            trench_dy = next_rect['x_end'] * scale_factor - y4
        elif idx > 0:
            prev_rect = self.sample_rects[idx - 1]
            trench_dx = x4 - prev_rect['y_end'] * scale_factor
            trench_dy = y4 - prev_rect['x_end'] * scale_factor
        else:
            trench_dx = x4 - x1
            trench_dy = y4 - y1

        # 归一化方向向量
        trench_len = math.sqrt(trench_dx * trench_dx + trench_dy * trench_dy)
        if trench_len < 0.001:
            trench_dx, trench_dy = 1.0, 0.0
        trench_dx /= trench_len
        trench_dy /= trench_len

        # 垂直方向
        perp_x = -trench_dy
        perp_y = trench_dx

        # 根据sample_side确定厚度偏移方向
        thickness_sign = -self.sample_side
        offset_magnitude = self.sample_thickness * thickness_sign * 1.5 * scale_factor  # 标注在矩形外侧

        # 标注位置在矩形外侧的中点
        mid_x = (x1 + x4) / 2 + perp_x * offset_magnitude
        mid_y = (y1 + y4) / 2 + perp_y * offset_magnitude

        # 写入TEXT实体
        sample_id = rect['sample_id']
        if sample_id == '非采样区':
            return  # 非采样区不标注

        f.write("  0\n")
        f.write("TEXT\n")
        f.write("  8\n")
        f.write("LABEL\n")
        f.write("  62\n")
        f.write("3\n")  # 黄色
        f.write("  10\n")
        f.write(f"{mid_x:.6f}\n")
        f.write("  20\n")
        f.write(f"{mid_y:.6f}\n")
        f.write("  30\n")
        f.write("0.0\n")
        f.write("  40\n")
        f.write("1.0\n")  # 文字高度
        f.write("  72\n")
        f.write("1\n")  # 居中对齐
        f.write("  73\n")
        f.write("2\n")  # 垂直居中
        f.write("  11\n")
        f.write(f"{mid_x:.6f}\n")
        f.write("  21\n")
        f.write(f"{mid_y:.6f}\n")
        f.write("  31\n")
        f.write("0.0\n")
        f.write("  1\n")
        f.write(f"{sample_id}\n")

    def _write_sample_rect(self, f, sample: SampleArea, scale_factor: float):
        """绘制样品矩形区域（使用HATCH实体填充）

        按钻孔软件方案：
        - 颜色：黑色=7，白色=9（Section映射）
        - HATCH格式：100 AcDbHatch、70=1（实体填充）
        - 四条边全画，保证边界闭合
        """
        # 使用st_to_world计算四个角点的世界坐标
        p1 = self.st_to_world(sample.s_start, sample.t_near)  # 起点-贴槽
        p2 = self.st_to_world(sample.s_start, sample.t_far)   # 起点-远侧
        p3 = self.st_to_world(sample.s_end, sample.t_far)     # 终点-远侧
        p4 = self.st_to_world(sample.s_end, sample.t_near)   # 终点-贴槽

        # 应用起点偏移和比例尺
        # 顺序：p1→p2→p3→p4→p1（闭合）
        polygon = [
            (self.start_x + p1[0] * scale_factor, self.start_y + p1[1] * scale_factor),
            (self.start_x + p2[0] * scale_factor, self.start_y + p2[1] * scale_factor),
            (self.start_x + p3[0] * scale_factor, self.start_y + p3[1] * scale_factor),
            (self.start_x + p4[0] * scale_factor, self.start_y + p4[1] * scale_factor),
        ]

        # 颜色映射：黑色=7，白色=8，橙色=30
        if sample.color_index == 0:
            color = 8   # 白色
        elif sample.color_index == 1:
            color = 7  # 黑色
        elif sample.color_index == 3:
            color = 30  # 橙色
        else:
            color = 8  # 灰色（备用）

        # 1. 绘制4条边（LINE实体，四条边全画保证边界闭合）
        for i in range(4):
            pt1 = polygon[i]
            pt2 = polygon[(i + 1) % 4]

            f.write("  0\n")
            f.write("LINE\n")
            f.write("  8\n")
            f.write("SAMPLE\n")
            f.write("  62\n")
            f.write(f"{color}\n")

            f.write("  10\n")
            f.write(f"{pt1[0]:.6f}\n")
            f.write("  20\n")
            f.write(f"{pt1[1]:.6f}\n")
            f.write("  30\n")
            f.write("0.0\n")

            f.write("  11\n")
            f.write(f"{pt2[0]:.6f}\n")
            f.write("  21\n")
            f.write(f"{pt2[1]:.6f}\n")
            f.write("  31\n")
            f.write("0.0\n")

        # 2. 绘制HATCH实体（实体填充）
        # 按钻孔软件验证的模板
        f.write("  0\n")
        f.write("HATCH\n")
        f.write("100\n")
        f.write("AcDbEntity\n")
        f.write("  8\n")
        f.write("SAMPLE_FILL\n")          # 图层名
        f.write(" 62\n")
        f.write(f"{color}\n")             # 颜色索引
        f.write("100\n")
        f.write("AcDbHatch\n")           # 子类标记，必须有
        f.write(" 10\n")
        f.write("0.0\n")
        f.write(" 20\n")
        f.write("0.0\n")
        f.write(" 30\n")
        f.write("0.0\n")                 # 高程点
        f.write("210\n")
        f.write("0.0\n")
        f.write("220\n")
        f.write("0.0\n")
        f.write("230\n")
        f.write("1.0\n")                 # 挤出方向
        f.write("  2\n")
        f.write("SOLID\n")               # 图案名：SOLID
        f.write(" 70\n")
        f.write("1\n")                   # 1 = 实体填充
        f.write(" 71\n")
        f.write("0\n")                   # 0 = 非关联
        f.write(" 91\n")
        f.write("1\n")                   # 边界路径数量 = 1
        f.write(" 92\n")
        f.write("2\n")                   # 2 = 多段线边界
        f.write(" 72\n")
        f.write("0\n")                   # 无凸度
        f.write(" 73\n")
        f.write("1\n")                   # 1 = 闭合
        f.write(" 93\n")
        f.write("4\n")                   # 顶点数 = 4
        for x, y in polygon:
            f.write(" 10\n")
            f.write(f"{x:.6f}\n")
            f.write(" 20\n")
            f.write(f"{y:.6f}\n")
        f.write(" 75\n")
        f.write("0\n")                   # 填充样式：普通
        f.write(" 76\n")
        f.write("1\n")                   # 图案类型：预定义

    def _write_start_marker(self, f, profile: TrenchProfile, scale_factor: float):
        """绘制起点标记（绿色十字叉）

        坐标系统与预览一致，使用XY交换 (x_图, y_图) = (Y_投影, X_投影)
        """
        if not self.world_points:
            return

        # XY交换
        proj_x, proj_y = self.world_points[0]
        x = proj_y * scale_factor  # Y_投影 -> x_图
        y = proj_x * scale_factor  # X_投影 -> y_图
        size = 1.0

        # 绘制十字叉（两条垂直相交的线）
        # 水平线
        f.write("  0\n")
        f.write("LINE\n")
        f.write("  8\n")
        f.write("MARKER\n")
        f.write(" 62\n")
        f.write("3\n")  # 绿色

        f.write("  10\n")
        f.write(f"{x - size:.6f}\n")
        f.write("  20\n")
        f.write(f"{y:.6f}\n")
        f.write("  30\n")
        f.write("0.0\n")

        f.write("  11\n")
        f.write(f"{x + size:.6f}\n")
        f.write("  21\n")
        f.write(f"{y:.6f}\n")
        f.write("  31\n")
        f.write("0.0\n")

        # 垂直线
        f.write("  0\n")
        f.write("LINE\n")
        f.write("  8\n")
        f.write("MARKER\n")
        f.write(" 62\n")
        f.write("3\n")  # 绿色

        f.write("  10\n")
        f.write(f"{x:.6f}\n")
        f.write("  20\n")
        f.write(f"{y - size:.6f}\n")
        f.write("  30\n")
        f.write("0.0\n")

        f.write("  11\n")
        f.write(f"{x:.6f}\n")
        f.write("  21\n")
        f.write(f"{y + size:.6f}\n")
        f.write("  31\n")
        f.write("0.0\n")


def generate_tc_dxf(output_path: str, projection_data: List[Dict[str, Any]],
                    trench_id: str, azimuth: float = 0.0,
                    sample_thickness: float = 2.0, scale: int = 500,
                    sample_side: int = -1, start_x: float = 0.0, start_y: float = 0.0):
    """快捷函数：生成探槽样品区DXF文件

    Args:
        output_path: 输出DXF文件路径
        projection_data: 样轨投影表数据
        trench_id: 探槽编号
        azimuth: 探槽方位角
        sample_thickness: 样品区域厚度（图面单位）
        scale: 比例尺，如500
        sample_side: 样品位置，-1=左侧, +1=右侧
        start_x: 起点X坐标
        start_y: 起点Y坐标
    """
    writer = TCDXFWriter()
    writer.set_params(sample_thickness, scale, sample_side)
    writer.set_start_coords(start_x, start_y)
    writer.load_from_projection_data(trench_id, projection_data, azimuth)
    writer.write_dxf_file(output_path)
