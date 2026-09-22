# -*- coding: utf-8 -*-
"""
探槽样品区预览控件 V3
作者：消化

功能：
- 预览探槽剖面图
- 支持鼠标拖拽平移
- 支持滚轮缩放
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from PyQt5.QtWidgets import QWidget, QMenu, QSizePolicy
from PyQt5.QtCore import Qt, QPoint, QPointF, pyqtSignal, QSize
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QMouseEvent, QWheelEvent, QResizeEvent, QPolygon


class SampleRect:
    """样品矩形（使用世界坐标）"""
    def __init__(self, x_start: float, y_start: float, x_end: float, y_end: float,
                 sample_id: str, color_index: int = 0,
                 start_idx: int = -1, end_idx: int = -1):
        """
        Args:
            x_start: 起点世界坐标X
            y_start: 起点世界坐标Y
            x_end: 终点世界坐标X
            y_end: 终点世界坐标Y
            sample_id: 样品编号
            color_index: 颜色索引
            start_idx: 起点在world_points中的索引
            end_idx: 终点在world_points中的索引
        """
        self.x_start = x_start
        self.y_start = y_start
        self.x_end = x_end
        self.y_end = y_end
        self.sample_id = sample_id
        self.color_index = color_index
        self.start_idx = start_idx
        self.end_idx = end_idx


class PreviewWidget(QWidget):
    """探槽剖面图预览控件"""

    # 信号：视图参数改变 / 鼠标坐标改变
    view_changed = pyqtSignal()
    mouse_moved = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)

        # 视图变换参数
        self.offset_x = 50  # X方向偏移（deprecated，用origin_x代替）
        self.offset_y = 300  # Y方向偏移（deprecated，用origin_y代替）
        self.scale = 1.0  # 缩放比例
        self._auto_scale = True  # 是否自动缩放

        # 统一映射参数
        self._origin_x = 50  # 屏幕原点X
        self._origin_y = 550  # 屏幕原点Y（画布底部）
        self._center_x = 0.0  # 图面缩放中心X
        self._center_y = 0.0  # 图面缩放中心Y
        self._scale = 1.0  # 缩放比例

        # 数据
        self.trench_length = 0.0  # 探槽总长度
        self.sample_rects = []  # 样品矩形列表
        self.sample_side = -1  # -1=左侧, +1=右侧
        self.show_labels = True
        self._mouse_x = 0.0  # 鼠标世界坐标X
        self._mouse_y = 0.0  # 鼠标世界坐标Y

        # 图面映射参数（交换XY后用于Y翻转）
        self._margin = 50
        self._draw_h = 400
        self._y_min = 0.0
        self._y_range = 1.0

        # 探槽信息（用于显示）
        self.start_x = 0.0  # 起点世界坐标X
        self.start_y = 0.0  # 起点世界坐标Y
        self.start_azimuth = 0.0  # 起始方位角
        self.total_azimuth = 0.0  # 总方位角
        self.segments = []  # 探槽段列表 [(azimuth, length), ...]

        # 两套坐标体系：
        # real_world_points - 真实坐标（来自Excel原始数据）
        # figure_world_points - 图面坐标（真实坐标 × scale_factor），用于绘制和DXF导出
        self.real_world_points = []  # 真实世界坐标点列表
        self.figure_world_points = []  # 图面坐标点列表

        # 比例尺相关
        self.input_scale = 1000  # 输入数据比例尺（Excel原始数据）
        self.output_scale = 1000  # 输出比例尺（用户设置）
        self.scale_factor = 1.0  # 换算因子 = input_scale / output_scale

        # 整体移动偏移量（保留，用于比例尺切换时重新应用）
        self.move_delta_x = 0.0
        self.move_delta_y = 0.0

        # 颜色：0=白色(H样品), 1=黑色(H样品), 2=灰色(非采样区)
        self.colors = [QColor(255, 255, 255), QColor(0, 0, 0), QColor(200, 200, 200)]

        # 探槽壁参数
        self.wall_offset = 5.0  # 探槽壁偏移距离
        self.show_walls = True  # 是否显示探槽壁
        self.cd_points = []  # CD线坐标（用于DXF导出，与Preview共享）

        # 画笔
        self.line_pen = QPen(QColor(255, 0, 0), 2)  # 探槽线红色
        self.wall_pen = QPen(QColor(180, 0, 180), 2)  # 探槽壁洋红色
        self.border_pen = QPen(QColor(0, 0, 0), 1)
        self.text_pen = QPen(QColor(0, 128, 0), 1)  # 绿色标注
        self.start_marker_pen = QPen(QColor(0, 0, 255), 2)  # 起点标记蓝色
        self.info_pen = QPen(QColor(100, 100, 100), 1)  # 信息文字灰色

        self.setMinimumSize(800, 400)
        # 设置尺寸策略：水平方向扩展，垂直方向固定
        size_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        size_policy.setHorizontalStretch(1)
        size_policy.setVerticalStretch(0)
        self.setSizePolicy(size_policy)
        self.set_background_color(QColor(255, 255, 255))
        self.setMouseTracking(True)  # 启用鼠标追踪

    def set_background_color(self, color: QColor):
        """设置背景色"""
        self.background_color = color
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), color)
        self.setPalette(palette)

    def set_data(self, trench_length: float, sample_rects: list, sample_side: int = -1,
                 start_x: float = 0.0, start_y: float = 0.0, start_azimuth: float = 0.0,
                 total_azimuth: float = 0.0, segments: list = None, thickness_m: float = 1.0,
                 projection_data: list = None,
                 wall_offset: float = 5.0, show_walls: bool = True,
                 trench_id: str = "", sample_count: int = 0):
        """设置数据

        Args:
            trench_length: 探槽总长度（实际长度，米）
            sample_rects: 样品矩形列表
            sample_side: 样品显示在左侧(-1)还是右侧(+1)
            start_x: 起点世界坐标X
            start_y: 起点世界坐标Y
            start_azimuth: 起始方位角
            total_azimuth: 总方位角
            segments: 探槽段列表 [(azimuth, length), ...]
            thickness_m: 样品厚度（米）
            projection_data: 投影表数据列表，每行包含X, Y坐标
            wall_offset: 探槽壁偏移距离（与样品同侧）
            show_walls: 是否显示探槽壁
            trench_id: 探槽编号
            sample_count: 样品数量
        """
        # 保存探槽信息
        self.trench_id = trench_id
        self.sample_count = sample_count

        print(f"[Preview] set_data called: trench_id={trench_id}, trench_length={trench_length}, "
              f"sample_count={sample_count}, side={sample_side}, azimuth={start_azimuth}, "
              f"wall_offset={wall_offset}, show_walls={show_walls}")

        # 更新探槽壁参数
        self.wall_offset = wall_offset
        self.show_walls = show_walls

        # 检查投影数据是否真正改变（用于判断是否需要重新生成sample_rects）
        # 比较内容而不是对象引用
        data_changed = True
        if hasattr(self, '_last_projection_data') and self._last_projection_data is not None:
            if self._last_projection_data is projection_data:
                # 同一个对象，内容肯定相同
                data_changed = False
                print(f"[Preview] set_data: projection_data same object, preserving existing sample_rects")
            elif len(self._last_projection_data) == len(projection_data):
                # 长度相同，比较内容
                same = True
                for i, row in enumerate(projection_data):
                    last_row = self._last_projection_data[i]
                    if (row.get('样号') != last_row.get('样号') or
                        row.get('X') != last_row.get('X') or
                        row.get('Y') != last_row.get('Y')):
                        same = False
                        break
                if same:
                    data_changed = False
                    print(f"[Preview] set_data: projection_data content unchanged, preserving existing sample_rects")

        self._last_projection_data = projection_data

        # 如果数据未改变，且已有sample_rects（已缩放的），则保留
        # 但仍需要更新sample_side和wall_offset，因为可能改变了这些参数
        if not data_changed and hasattr(self, '_rects_scaled') and self._rects_scaled:
            # 检查是否有参数变化需要重新计算_boundary_perps
            params_changed = (
                self.sample_side != sample_side or
                self.wall_offset != wall_offset or
                self.show_walls != show_walls
            )
            # 更新显示参数
            self.trench_length = trench_length
            self.sample_side = sample_side
            self.start_x = start_x
            self.start_y = start_y
            self.start_azimuth = start_azimuth
            self.total_azimuth = total_azimuth
            self.segments = segments if segments else []
            self.thickness_m = thickness_m
            self.wall_offset = wall_offset
            self.show_walls = show_walls
            # 如果参数变化导致CD线位置变化，需要重新计算_boundary_perps
            if params_changed:
                self._precalculate_boundary_perps()
            # 刷新视图
            self.update()
            print(f"[Preview] set_data: data unchanged, updated params, sample_side={sample_side} (self.sample_side={self.sample_side}), params_changed={params_changed}")
            return

        self.trench_length = trench_length
        self.sample_rects = sample_rects
        self.sample_side = sample_side
        self.start_x = start_x
        self.start_y = start_y
        self.start_azimuth = start_azimuth
        self.total_azimuth = total_azimuth
        self.segments = segments if segments else []
        self.thickness_m = thickness_m
        self.projection_data = projection_data if projection_data else []

        # 1. 重置视图状态和坐标标志
        self._reset_view()
        # 注意：sample_rects已经在main.py的update_preview中按当前scale_ratio缩放过了
        # 所以需要标记为已缩放，避免set_output_scale时重复缩放
        self._rects_scaled = True
        self._moved = False

        # 2. 计算探槽线的世界坐标点（直接从投影表数据）
        self._calculate_world_points()

        # 3. 更新样品矩形的起止索引
        self._update_sample_indices()

        # 4. 跳过s坐标归一化（现在使用世界坐标直接绘制）
        # 5. 重新计算缩放比例
        self._recalculate_scale()

        # 6. 预计算边界垂线（用于样品区和CD线）
        self._precalculate_boundary_perps()

        # 5. 刷新视图
        self.update()
        print(f"[Preview] update() called, widget size: {self.width()}x{self.height()}, scale={self.scale}")

    def _reset_view(self):
        """重置视图状态（切换探槽时调用）"""
        self.offset_x = 50
        self.offset_y = self.height() / 2 if self.height() > 0 else 300
        self.scale = 1.0
        self.view_changed.emit()

    def _normalize_sample_s(self):
        """统一样品s坐标累积源

        确保样品的s_start/s_end与探槽线segments累积保持一致。
        如果投影表X值与segments累积不一致，以segments为准重新计算。
        同时验证st_to_world(s, 0) == s_to_world(s)。

        注意：现在使用世界坐标，直接返回跳过此函数
        """
        # 新版本使用世界坐标，不需要s归一化
        return

    def _calculate_world_points(self):
        """计算探槽线的世界坐标点（真实坐标）

        直接从投影表数据的每一行X,Y坐标构建轨迹点。
        投影表第一行X=0, Y=0是起点。
        注意：这里存储的是真实坐标（real_world_points），后续会转换为图面坐标。
        """
        self.real_world_points = []

        # 直接从投影表数据获取每一行的X,Y坐标
        if self.projection_data:
            for row in self.projection_data:
                x = row.get('X', 0) or 0
                y = row.get('Y', 0) or 0
                self.real_world_points.append((x, y))

            # 确保起点是(0, 0) - 如果第一个点不是(0, 0)，在前面插入起点
            # 这样轨迹从原点开始，符合投影表的定义
            if self.real_world_points and (self.real_world_points[0][0] != 0 or self.real_world_points[0][1] != 0):
                self.real_world_points.insert(0, (0.0, 0.0))

        # 如果没有投影表数据，回退到使用sample_rects
        if not self.real_world_points and self.sample_rects:
            for rect in self.sample_rects:
                self.real_world_points.append((rect.x_end, rect.y_end))

        # 如果仍然没有点，使用原点
        if not self.real_world_points:
            self.real_world_points = [(0.0, 0.0)]

        print(f"[Preview] _calculate_world_points: {len(self.real_world_points)} points from projection_data")
        for i, PT in enumerate(self.real_world_points[:10]):
            print(f"  point {i}: ({PT[0]:.2f}, {PT[1]:.2f})")
        if len(self.real_world_points) > 10:
            print(f"  ... and {len(self.real_world_points) - 10} more points")

        # 计算图面坐标：真实坐标 × scale_factor + 整体移动偏移
        self._apply_scale_factor()

    def _apply_scale_factor(self):
        """从真实坐标计算图面坐标

        figure_world_points = real_world_points × scale_factor + move_delta
        比例尺切换时调用此方法重新计算。
        """
        self.figure_world_points = []
        for x, y in self.real_world_points:
            fig_x = x * self.scale_factor + self.move_delta_x
            fig_y = y * self.scale_factor + self.move_delta_y
            self.figure_world_points.append((fig_x, fig_y))

        print(f"[Preview] _apply_scale_factor: scale_factor={self.scale_factor}, move_delta=({self.move_delta_x}, {self.move_delta_y})")
        print(f"[Preview] figure_world_points[0] = {self.figure_world_points[0] if self.figure_world_points else 'empty'}")

    def set_output_scale(self, output_scale: int):
        """设置输出比例尺，重新计算图面坐标

        Args:
            output_scale: 新的输出比例尺（如2000表示1:2000）
        """
        self.output_scale = output_scale
        old_scale_factor = self.scale_factor
        self.scale_factor = self.input_scale / output_scale
        print(f"[Preview] set_output_scale: output_scale={output_scale}, scale_factor={self.scale_factor}")

        # 需要重新计算 sample_rects 的坐标（同步缩放）
        if self.sample_rects:
            if getattr(self, '_moved', False):
                # 已经移动过：sample_rects 是旧图面坐标
                # 还原到真实坐标，再应用新scale_factor
                for rect in self.sample_rects:
                    # 从旧图面坐标还原到真实坐标
                    real_x_start = (rect.x_start - self.move_delta_x) / old_scale_factor if old_scale_factor != 0 else rect.x_start
                    real_y_start = (rect.y_start - self.move_delta_y) / old_scale_factor if old_scale_factor != 0 else rect.y_start
                    real_x_end = (rect.x_end - self.move_delta_x) / old_scale_factor if old_scale_factor != 0 else rect.x_end
                    real_y_end = (rect.y_end - self.move_delta_y) / old_scale_factor if old_scale_factor != 0 else rect.y_end
                    # 重新计算为新图面坐标
                    rect.x_start = real_x_start * self.scale_factor + self.move_delta_x
                    rect.y_start = real_y_start * self.scale_factor + self.move_delta_y
                    rect.x_end = real_x_end * self.scale_factor + self.move_delta_x
                    rect.y_end = real_y_end * self.scale_factor + self.move_delta_y
            else:
                # 还没有移动过：sample_rects 是真实坐标
                for rect in self.sample_rects:
                    rect.x_start = rect.x_start * self.scale_factor
                    rect.y_start = rect.y_start * self.scale_factor
                    rect.x_end = rect.x_end * self.scale_factor
                    rect.y_end = rect.y_end * self.scale_factor

        # 重新计算图面坐标（保留move_delta）
        self._apply_scale_factor()

        # 重新计算缩放比例以适应新的图面坐标范围
        self._recalculate_scale()

        # 更新样品矩形的索引（基于新的figure_world_points）
        # 注意：sample_rects 的坐标已经更新为新图面坐标，标记 _rects_scaled
        self._rects_scaled = True
        self._update_sample_indices()

        # 刷新视图
        self.update()

    def _update_sample_indices(self):
        """更新样品矩形的起止索引

        根据 sample_rects 的起止坐标，在 figure_world_points 中找到对应的索引。
        由于浮点精度问题，使用近似匹配。

        注意：如果 _rects_scaled=True，则 sample_rects 已经是图面坐标（不再需要乘 scale_factor）
        """
        if not self.figure_world_points or not self.sample_rects:
            return

        # 建立坐标到索引的映射（使用元组key）
        coord_to_idx = {}
        for i, pt in enumerate(self.figure_world_points):
            coord_to_idx[(round(pt[0], 3), round(pt[1], 3))] = i

        # 为每个 sample_rect 找到起止索引
        for rect in self.sample_rects:
            # 如果已经缩放过（_rects_scaled=True），sample_rects 已经是图面坐标，直接使用
            if getattr(self, '_rects_scaled', False):
                start_key = (round(rect.x_start, 3), round(rect.y_start, 3))
                end_key = (round(rect.x_end, 3), round(rect.y_end, 3))
            else:
                # 真实坐标需要乘以 scale_factor
                start_key = (round(rect.x_start * self.scale_factor + self.move_delta_x, 3),
                             round(rect.y_start * self.scale_factor + self.move_delta_y, 3))
                end_key = (round(rect.x_end * self.scale_factor + self.move_delta_x, 3),
                           round(rect.y_end * self.scale_factor + self.move_delta_y, 3))

            rect.start_idx = coord_to_idx.get(start_key, -1)
            rect.end_idx = coord_to_idx.get(end_key, -1)

            print(f"[DEBUG] Sample {rect.sample_id}: start=({rect.x_start:.2f}, {rect.y_start:.2f}) idx={rect.start_idx}, "
                  f"end=({rect.x_end:.2f}, {rect.y_end:.2f}) idx={rect.end_idx}")

    def move_all(self, target_x: float, target_y: float):
        """整体移动：将探槽起点移动到目标图面坐标

        target是图面坐标，用户输入的就是"我希望DXF里探槽起点是这个数"。
        因为DXF存的就是图面坐标，输入即输出，所见即所得。

        Args:
            target_x: 目标起点X坐标（图面坐标）
            target_y: 目标起点Y坐标（图面坐标）
        """
        print(f"[Preview] move_all: target=({target_x}, {target_y})")
        print(f"[Preview] figure_world_points[0] before move = {self.figure_world_points[0] if self.figure_world_points else 'empty'}")

        if self.figure_world_points:
            # 当前图面起点
            cur_x, cur_y = self.figure_world_points[0]

            # 计算偏移（基于图面坐标）
            delta_x = target_x - cur_x
            delta_y = target_y - cur_y

            print(f"[Preview] original_start=({cur_x}, {cur_y})")
            print(f"[Preview] delta=({delta_x}, {delta_y})")

            # 累积 move_delta（用于比例尺切换时重建坐标）
            self.move_delta_x += delta_x
            self.move_delta_y += delta_y

            # 重新计算 figure_world_points（基于 real_world_points * scale_factor + move_delta）
            self._apply_scale_factor()

            # 移动 sample_rects：真实坐标 -> 图面坐标 + move_delta
            if not getattr(self, '_moved', False):
                # 第一次移动：需要缩放
                for rect in self.sample_rects:
                    rect.x_start = rect.x_start * self.scale_factor + self.move_delta_x
                    rect.y_start = rect.y_start * self.scale_factor + self.move_delta_y
                    rect.x_end = rect.x_end * self.scale_factor + self.move_delta_x
                    rect.y_end = rect.y_end * self.scale_factor + self.move_delta_y
            else:
                # 后续移动：只移动，不缩放
                for rect in self.sample_rects:
                    rect.x_start += delta_x
                    rect.y_start += delta_y
                    rect.x_end += delta_x
                    rect.y_end += delta_y

            # 标记已整体移动
            self._moved = True
            # 标记sample_rects已是图面坐标
            self._rects_scaled = True

            print(f"[Preview] figure_world_points[0] after move = {self.figure_world_points[0]}")
            print(f"[Preview] figure_world_points[1] after move = {self.figure_world_points[1] if len(self.figure_world_points) > 1 else 'N/A'}")

        # 更新起点坐标
        self.start_x = target_x
        self.start_y = target_y

        print(f"[Preview] _moved = True, move_delta=({self.move_delta_x}, {self.move_delta_y})")

        # 重新计算缩放比例以适应新的坐标范围
        self._recalculate_scale()

        # 刷新视图
        self.update()

    def s_to_world(self, s: float) -> Tuple[float, float]:
        """沿槽距离 s → 世界坐标

        Args:
            s: 沿探槽中心线累积的水平距离

        Returns:
            (world_x, world_y): 世界坐标
        """
        # 防御：检查segments和figure_world_points
        if not self.segments or not self.figure_world_points:
            return (s * self.scale_factor, 0.0)

        # 确保s在有效范围内
        if s < 0:
            s = 0.0

        # 遍历段，找到 s 落在哪一段
        acc = 0.0
        for i, (az, L) in enumerate(self.segments):
            if s <= acc + L or i == len(self.segments) - 1:
                local = s - acc
                # 该段起点世界坐标 = figure_world_points[i]
                if i >= len(self.figure_world_points):
                    i = len(self.figure_world_points) - 1
                base_x, base_y = self.figure_world_points[i]
                az_rad = math.radians(az)
                return (base_x + math.sin(az_rad) * local * self.scale_factor,
                        base_y + math.cos(az_rad) * local * self.scale_factor)
            acc += L

        # 超出范围，返回终点
        return self.figure_world_points[-1] if self.figure_world_points else (s * self.scale_factor, 0.0)

    def azimuth_at(self, s: float) -> float:
        """沿槽距离 s → 该段方位角

        Args:
            s: 沿探槽中心线累积的水平距离

        Returns:
            方位角（度）
        """
        if not self.segments:
            return 0.0

        acc = 0.0
        for i, (az, L) in enumerate(self.segments):
            if s <= acc + L or i == len(self.segments) - 1:
                return az
            acc += L

        return self.segments[-1][0] if self.segments else 0.0

    def st_to_world(self, s: float, t: float) -> Tuple[float, float]:
        """展开坐标 (s, t) → 世界坐标

        这是整个工具最核心的坐标转换函数。

        Args:
            s: 沿槽累积距离
            t: 横向距离（正=左侧，负=右侧）

        Returns:
            (world_x, world_y): 世界坐标
        """
        # 1. 沿槽位置
        base_x, base_y = self.s_to_world(s)

        # 2. 当前段方位角
        az_rad = math.radians(self.azimuth_at(s))

        # 3. 垂直方向向量（左侧为正）
        #    探槽方向 = (sin, cos)
        #    逆时针旋转90° = (-cos, sin)
        perp_x = -math.cos(az_rad)
        perp_y = math.sin(az_rad)

        # 4. 横向偏移
        return (base_x + perp_x * t,
                base_y + perp_y * t)

    def _recalculate_scale(self):
        """重新计算缩放比例和图面映射参数

        统一映射公式：
        screen_x = origin_x + (x_图 - center_x) * scale
        screen_y = origin_y - (y_图 - center_y) * scale
        """
        # 计算图面坐标范围
        if self.figure_world_points and len(self.figure_world_points) >= 2:
            xs = [p[0] for p in self.figure_world_points]
            ys = [p[1] for p in self.figure_world_points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
        elif self.trench_length > 0:
            min_x, max_x = 0, self.trench_length * self.scale_factor
            min_y, max_y = -self.trench_length * self.scale_factor, self.trench_length * self.scale_factor
        else:
            return

        # 获取当前窗口尺寸
        w = self.width()
        h = self.height()
        if w <= 0:
            w = 800
        if h <= 0:
            h = 600

        # 交换XY后的图面坐标范围: (x_图, y_图) = (Y_投影, X_投影)
        x_图_min = min_y
        x_图_max = max_y
        y_图_min = min_x
        y_图_max = max_x

        # 图面范围
        x_图_range = x_图_max - x_图_min
        y_图_range = y_图_max - y_图_min
        if x_图_range < 0.001:
            x_图_range = 1.0
        if y_图_range < 0.001:
            y_图_range = 1.0

        # 边距
        margin = 50

        # 可用绘制区域
        canvas_w = w - 2 * margin
        canvas_h = h - 2 * margin

        # 等比缩放：X和Y共用同一个scale
        raw_scale = min(canvas_w / x_图_range, canvas_h / y_图_range)
        self._scale = raw_scale * 0.8  # 留20%边距

        # 设置缩放中心为图面中心
        self._center_x = (x_图_min + x_图_max) / 2
        self._center_y = (y_图_min + y_图_max) / 2

        # 设置屏幕原点
        self._origin_x = margin
        self._origin_y = h - margin

        print(f"[Preview] scale={self._scale}, center=({self._center_x}, {self._center_y}), origin=({self._origin_x}, {self._origin_y})")

    def clear(self):
        """清空数据"""
        self.trench_length = 0.0
        self.sample_rects = []
        self.update()

    def reset_view(self):
        """重置视图"""
        self._reset_view()
        self.update()

    def _to_screen(self, x: float, y: float) -> QPointF:
        """将世界坐标转换为屏幕坐标

        统一映射公式：
        screen_x = origin_x + (x_图 - center_x) * scale
        screen_y = origin_y - (y_图 - center_y) * scale
        """
        # 交换XY: (x_图, y_图) = (Y_投影, X_投影)
        x_图 = y
        y_图 = x

        # 统一映射公式
        screen_x = self._origin_x + (x_图 - self._center_x) * self._scale
        screen_y = self._origin_y - (y_图 - self._center_y) * self._scale

        return QPointF(screen_x, screen_y)

    def _to_world(self, screen_x: float, screen_y: float) -> Tuple[float, float]:
        """将屏幕坐标转换为世界坐标（_to_screen的逆变换）"""
        # 逆变换
        x_图 = (screen_x - self._origin_x) / self._scale + self._center_x
        y_图 = -(screen_y - self._origin_y) / self._scale + self._center_y

        # 逆交换: (Y_投影, X_投影) = (x_图, y_图)
        x_proj = y_图
        y_proj = x_图

        return x_proj, y_proj

    def paintEvent(self, event):
        """绘制事件"""
        print(f"[Preview] paintEvent called, size: {self.width()}x{self.height()}, trench_length={self.trench_length}")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        try:
            # 绘制网格
            self._draw_grid(painter)

            if self.trench_length <= 0:
                print(f"[Preview] trench_length <= 0, returning")
                return

            # 调试：打印世界坐标信息
            if self.figure_world_points:
                print(f"[Preview] figure_world_points[0] = {self.figure_world_points[0]}")
                print(f"[Preview] figure_world_points[-1] = {self.figure_world_points[-1]}")
            print(f"[Preview] drawing: scale={self.scale}, offset=({self.offset_x}, {self.offset_y})")
            # 绘制探槽主线
            self._draw_trench_line(painter)

            # 绘制探槽壁轮廓
            if self.show_walls:
                self._draw_trench_walls(painter)

            # 绘制样品区域
            self._draw_sample_areas(painter)

            # 绘制样品号标注
            if self.show_labels:
                self._draw_labels(painter)

            # 绘制比例尺
            self._draw_scale_bar(painter)

            # 绘制鼠标坐标
            self._draw_mouse_coords(painter)
        except Exception as e:
            import traceback
            print(f"[Preview] Error in paintEvent: {e}")
            print(traceback.format_exc())
            # 绘制错误信息
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            painter.drawText(50, 50, f"预览错误: {str(e)}")

    def _draw_mouse_coords(self, painter: QPainter):
        """绘制鼠标坐标"""
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        font = QFont("Microsoft YaHei", 9)
        painter.setFont(font)

        # 在右下角显示坐标
        coord_text = f"X: {self._mouse_x:.2f}  Y: {self._mouse_y:.2f}"
        x = self.width() - 150
        y = self.height() - 15
        painter.drawText(int(x), int(y), coord_text)

    def _draw_grid(self, painter: QPainter):
        """绘制网格"""
        pen = QPen(QColor(230, 230, 230), 1)
        painter.setPen(pen)

        # 垂直线（每10米一条）
        grid_spacing = 10 * self.scale  # 每10米一个网格
        start_x = int(self.offset_x / grid_spacing) * grid_spacing

        for x in range(int(start_x), int(self.width()), int(grid_spacing)):
            painter.drawLine(int(x), 0, int(x), int(self.height()))

        # 水平线
        for y in range(0, int(self.height()), 50):
            painter.drawLine(0, int(y), int(self.width()), int(y))

        # 绘制坐标轴和方向指示（浅灰色，不干扰主图）
        self._draw_compass_north(painter)

    def _draw_compass_north(self, painter: QPainter):
        """绘制北方指示器和坐标轴标签"""
        pen = QPen(QColor(180, 180, 180), 1)  # 浅灰色
        painter.setPen(pen)
        font = QFont("Microsoft YaHei", 10)
        painter.setFont(font)

        # 在右上角绘制简化的坐标轴和N指示
        ax_x = self.width() - 80
        ax_y = self.height() - 60
        axis_len = 40

        # 绘制X轴（东向 -> 右）
        painter.drawLine(ax_x, ax_y, ax_x + axis_len, ax_y)
        painter.drawText(ax_x + axis_len + 5, ax_y + 5, "E")

        # 绘制Y轴（北向 -> 上）
        painter.drawLine(ax_x, ax_y, ax_x, ax_y - axis_len)
        painter.drawText(ax_x - 5, ax_y - axis_len - 5, "N")

    def _draw_trench_line(self, painter: QPainter):
        """绘制探槽主线（实际走向视图）"""
        painter.setPen(self.line_pen)

        # 如果有图面坐标点，绘制实际路径
        if self.figure_world_points and len(self.figure_world_points) >= 2:
            # 绘制多段线
            screen_points = [self._to_screen(p[0], p[1]) for p in self.figure_world_points]
            for i in range(len(screen_points) - 1):
                painter.drawLine(
                    int(screen_points[i].x()), int(screen_points[i].y()),
                    int(screen_points[i + 1].x()), int(screen_points[i + 1].y())
                )
        else:
            # 回退：绘制简单的水平线
            p1 = self._to_screen(0, 0)
            p2 = self._to_screen(self.trench_length * self.scale_factor, 0)
            painter.drawLine(p1, p2)

        # 绘制起点标记
        self._draw_start_marker(painter)

        # 绘制探槽信息
        self._draw_trench_info(painter)

    def _precalculate_boundary_perps(self):
        """预计算所有样品边界点的共用垂线方向

        这确保相邻样品在边界处使用相同的垂线方向，避免因段方向突变导致的样品区重叠
        同时也用于CD线的绘制
        """
        self._boundary_perps = {}  # idx -> (perp_x, perp_y)

        if not self.sample_rects or not hasattr(self, 'figure_world_points') or not self.figure_world_points:
            print("[Preview _precalculate_boundary_perps] early return: no sample_rects or figure_world_points")
            return

        # 调试日志
        print(f"[Preview _precalculate_boundary_perps] sample_rects={len(self.sample_rects)}, figure_world_points={len(self.figure_world_points)}")
        print(f"[Preview _precalculate_boundary_perps] sample_side={self.sample_side}")

        # 收集所有样品边界点索引
        boundary_indices = set()
        for rect in self.sample_rects:
            if hasattr(rect, 'start_idx') and rect.start_idx >= 0:
                boundary_indices.add(rect.start_idx)
            if hasattr(rect, 'end_idx') and rect.end_idx >= 0:
                boundary_indices.add(rect.end_idx)

        print(f"[Preview _precalculate_boundary_perps] boundary_indices count={len(boundary_indices)}, indices={sorted(boundary_indices)[:10]}...")

        # 为每个唯一边界索引计算垂线方向
        for idx in boundary_indices:
            if idx >= len(self.figure_world_points):
                continue

            p = self.figure_world_points[idx]

            # 计算该点处的切线方向
            if idx == 0:
                next_p = self.figure_world_points[idx + 1]
                dx = next_p[0] - p[0]
                dy = next_p[1] - p[1]
            elif idx == len(self.figure_world_points) - 1:
                prev_p = self.figure_world_points[idx - 1]
                dx = p[0] - prev_p[0]
                dy = p[1] - prev_p[1]
            else:
                prev_p = self.figure_world_points[idx - 1]
                next_p = self.figure_world_points[idx + 1]
                # 使用前后两点的平均方向
                dx = next_p[0] - prev_p[0]
                dy = next_p[1] - prev_p[1]

            seg_len = math.sqrt(dx * dx + dy * dy)
            if seg_len < 0.001:
                continue

            # 归一化切线
            dx /= seg_len
            dy /= seg_len

            # 垂线方向：perp = (-dy, dx)，然后根据sample_side调整方向
            perp_x = -dy * self.sample_side
            perp_y = dx * self.sample_side
            perp_len = math.sqrt(perp_x * perp_x + perp_y * perp_y)
            if perp_len > 0.001:
                perp_x /= perp_len
                perp_y /= perp_len
                self._boundary_perps[idx] = (perp_x, perp_y)

        print(f"[Preview _precalculate_boundary_perps] calculated {len(self._boundary_perps)} boundary perps")

    def get_boundary_perps(self):
        """获取预计算的边界垂线（用于DXF导出）

        Returns:
            dict: idx -> (perp_x, perp_y) 归一化的垂线向量
        """
        return getattr(self, '_boundary_perps', {})

    def _draw_trench_walls(self, painter: QPainter):
        """绘制探槽壁轮廓（4条线）

        探槽结构：
            D -------- C (另一壁，与样品同侧)
            |          |
            |  偏移距离 |
            |          |
            A -------- B (探槽主轴线)

        AB = 探槽主轴线
        CD = AB的等距平行线（每一段都垂直偏移wall_offset距离）

        偏移方向：与sample_side相同

        算法：按段处理，每段使用统一的垂直方向，避免在段交界处出现锯齿
        """
        if not self.figure_world_points or len(self.figure_world_points) < 2:
            return

        # 调试日志
        print(f"[Preview _draw_trench_walls] figure_world_points[0]={self.figure_world_points[0]}, [-1]={self.figure_world_points[-1]}")
        print(f"[Preview _draw_trench_walls] sample_side={self.sample_side}, wall_offset={self.wall_offset}")
        print(f"[Preview _draw_trench_walls] _boundary_perps count={len(getattr(self, '_boundary_perps', {}))}")

        painter.setPen(self.wall_pen)

        n = len(self.figure_world_points)

        # 如果有segments信息，使用共用边界垂线逻辑；否则按点处理
        if self.segments and len(self.segments) > 0 and hasattr(self, '_boundary_perps') and self._boundary_perps:
            # 使用预计算的共用边界垂线（与样品区共用边界的逻辑一致）
            cd_points = []
            for i, p in enumerate(self.figure_world_points):
                # 计算当前点的切线方向
                if i == 0:
                    next_p = self.figure_world_points[i + 1]
                    dx = next_p[0] - p[0]
                    dy = next_p[1] - p[1]
                elif i == n - 1:
                    prev = self.figure_world_points[i - 1]
                    dx = p[0] - prev[0]
                    dy = p[1] - prev[1]
                else:
                    prev = self.figure_world_points[i - 1]
                    next_p = self.figure_world_points[i + 1]
                    dx = next_p[0] - prev[0]
                    dy = next_p[1] - prev[1]

                seg_len = math.sqrt(dx * dx + dy * dy)
                if seg_len < 0.001:
                    if i > 0:
                        prev = self.figure_world_points[i - 1]
                        dx = p[0] - prev[0]
                        dy = p[1] - prev[1]
                        seg_len = math.sqrt(dx * dx + dy * dy)

                if seg_len < 0.001:
                    continue

                # 检查是否有预计算的共用边界垂线
                if i in self._boundary_perps:
                    perp_x, perp_y = self._boundary_perps[i]
                else:
                    # 归一化切线方向
                    dx /= seg_len
                    dy /= seg_len
                    # 左手边法向量 = (-dy, dx)
                    perp_x = -dy * self.sample_side
                    perp_y = dx * self.sample_side
                    perp_len = math.sqrt(perp_x * perp_x + perp_y * perp_y)
                    if perp_len > 0.001:
                        perp_x /= perp_len
                        perp_y /= perp_len

                # 计算偏移点
                offset_x = p[0] + self.wall_offset * perp_x
                offset_y = p[1] + self.wall_offset * perp_y
                cd_points.append((offset_x, offset_y))

            # 保存CD点坐标（用于DXF导出）
            self.cd_points = cd_points
            print(f"[Preview] cd_points(第一分支)计算完成，长度={len(cd_points)}, wall_offset={self.wall_offset}")
            print(f"[Preview] cd_points[0]={cd_points[0] if cd_points else 'empty'}")
            print(f"[Preview] cd_points[-1]={cd_points[-1] if cd_points else 'empty'}")

            if len(cd_points) >= 2:
                # 绘制CD线（连续的多段线）
                for i in range(len(cd_points) - 1):
                    p1_screen = self._to_screen(cd_points[i][0], cd_points[i][1])
                    p2_screen = self._to_screen(cd_points[i + 1][0], cd_points[i + 1][1])
                    painter.drawLine(int(p1_screen.x()), int(p1_screen.y()),
                                   int(p2_screen.x()), int(p2_screen.y()))

                # 绘制槽头和槽尾
                a_screen = self._to_screen(self.figure_world_points[0][0], self.figure_world_points[0][1])
                d_screen = self._to_screen(cd_points[0][0], cd_points[0][1])
                painter.drawLine(int(a_screen.x()), int(a_screen.y()),
                               int(d_screen.x()), int(d_screen.y()))

                b_screen = self._to_screen(self.figure_world_points[-1][0], self.figure_world_points[-1][1])
                c_screen = self._to_screen(cd_points[-1][0], cd_points[-1][1])
                painter.drawLine(int(b_screen.x()), int(b_screen.y()),
                               int(c_screen.x()), int(c_screen.y()))
        else:
            # 回退到按点处理（旧算法）
            cd_points = []
            for i, p in enumerate(self.figure_world_points):
                if i == n - 1:
                    prev = self.figure_world_points[i - 1]
                    dx = p[0] - prev[0]
                    dy = p[1] - prev[1]
                else:
                    next_p = self.figure_world_points[i + 1]
                    dx = next_p[0] - p[0]
                    dy = next_p[1] - p[1]

                seg_len = math.sqrt(dx * dx + dy * dy)
                if seg_len < 0.001:
                    if i > 0:
                        prev = self.figure_world_points[i - 1]
                        dx = p[0] - prev[0]
                        dy = p[1] - prev[1]
                        seg_len = math.sqrt(dx * dx + dy * dy)

                if seg_len < 0.001:
                    continue

                perp_x = -dy * self.sample_side
                perp_y = dx * self.sample_side
                perp_len = math.sqrt(perp_x * perp_x + perp_y * perp_y)

                if perp_len < 0.001:
                    continue

                norm_perp_x = perp_x / perp_len
                norm_perp_y = perp_y / perp_len

                offset_x = p[0] + self.wall_offset * norm_perp_x
                offset_y = p[1] + self.wall_offset * norm_perp_y
                cd_points.append((offset_x, offset_y))

            # 保存CD点坐标（用于DXF导出）
            self.cd_points = cd_points
            print(f"[Preview] cd_points(备用分支)计算完成，长度={len(cd_points)}, wall_offset={self.wall_offset}")
            print(f"[Preview] cd_points[0]={cd_points[0] if cd_points else 'empty'}")
            print(f"[Preview] cd_points[-1]={cd_points[-1] if cd_points else 'empty'}")

            if len(cd_points) >= 2:
                for i in range(len(cd_points) - 1):
                    p1_screen = self._to_screen(cd_points[i][0], cd_points[i][1])
                    p2_screen = self._to_screen(cd_points[i + 1][0], cd_points[i + 1][1])
                    painter.drawLine(int(p1_screen.x()), int(p1_screen.y()),
                                   int(p2_screen.x()), int(p2_screen.y()))

                # AC和BD
                a_screen = self._to_screen(self.figure_world_points[0][0], self.figure_world_points[0][1])
                d_screen = self._to_screen(cd_points[0][0], cd_points[0][1])
                painter.drawLine(int(a_screen.x()), int(a_screen.y()),
                               int(d_screen.x()), int(d_screen.y()))

                b_screen = self._to_screen(self.figure_world_points[-1][0], self.figure_world_points[-1][1])
                c_screen = self._to_screen(cd_points[-1][0], cd_points[-1][1])
                painter.drawLine(int(b_screen.x()), int(b_screen.y()),
                               int(c_screen.x()), int(c_screen.y()))

    def _draw_start_marker(self, painter: QPainter):
        """绘制原点标记（绿色十字叉）"""
        if not self.figure_world_points or len(self.figure_world_points) < 2:
            return

        # 绿色十字叉
        cross_pen = QPen(QColor(0, 200, 0), 2)  # 绿色
        painter.setPen(cross_pen)

        # 使用探槽实际起点（第一个figure_world_point）
        start_x, start_y = self.figure_world_points[0]
        start_screen = self._to_screen(start_x, start_y)

        # 绘制十字叉
        size = 12
        x = int(start_screen.x())
        y = int(start_screen.y())

        # 水平线
        painter.drawLine(x - size, y, x + size, y)
        # 垂直线
        painter.drawLine(x, y - size, x, y + size)

        # 在标记旁边显示起点坐标
        painter.setPen(self.info_pen)
        font = QFont("Microsoft YaHei", 8)
        painter.setFont(font)
        painter.drawText(x + size + 5, y + 4, f"起点({start_x:.1f},{start_y:.1f})")

    def _draw_trench_info(self, painter: QPainter):
        """绘制探槽信息"""
        painter.setPen(self.info_pen)
        font = QFont("Microsoft YaHei", 9)
        painter.setFont(font)

        # 获取探槽编号（默认显示"未选择"）
        trench_id = getattr(self, 'trench_id', '')
        if not trench_id:
            trench_id = "未选择"

        # 获取样品数量（默认显示0）
        sample_count = getattr(self, 'sample_count', 0)
        if sample_count == 0:
            sample_count = len([r for r in self.sample_rects if hasattr(r, 'sample_id') and r.sample_id != '非采样区']) if self.sample_rects else 0

        # 导线数
        segment_count = len(self.segments) if self.segments else 0

        # 探槽壁偏移方向
        side_str = "左侧" if self.sample_side == -1 else "右侧"

        # 样品厚度
        thickness = getattr(self, 'thickness_m', 0)

        # 当前比例尺
        output_scale = getattr(self, 'output_scale', 1000)

        # 在左上角显示探槽信息
        info_lines = [
            f"探槽编号: {trench_id}",
            f"当前比例尺: 1:{output_scale}",
            f"探槽长度: {self.trench_length:.2f} m",
            f"起始方位: {self.start_azimuth:.1f}°",
            f"导线数: {segment_count} 段",
            f"样品数量: {sample_count} 个",
            f"样品厚度: {thickness:.1f} mm",
            f"探槽壁偏移: {self.wall_offset}mm ({side_str})"
        ]
        for i, line in enumerate(info_lines):
            painter.drawText(10, 20 + i * 18, line)

    def _draw_sample_areas(self, painter: QPainter):
        """绘制样品区域（顺手壁单侧偏移造区）

        核心逻辑：
        1. 轨迹线图面坐标 (x_图, y_图) = (Y_投影, X_投影)
        2. 顺手壁 = 前进方向左手边，法向量 = (-dy, dx) 归一化
        3. 所有样品统一朝顺手壁方向偏移该样品厚度
        4. 样品区 = 子线段原线 + 偏移线，首尾闭合

        关键改进：相邻样品共用边界线，在段交界处使用统一切线方向的垂线，
        避免因段方向突变导致的样品区重叠

        Args:
            painter: QPainter对象
        """
        if not self.sample_rects:
            print("[DEBUG] _draw_sample_areas: no sample_rects")
            return

        if not self.figure_world_points:
            print("[DEBUG] _draw_sample_areas: no figure_world_points")
            return

        print(f"[DEBUG] _draw_sample_areas: {len(self.sample_rects)} rects, {len(self.figure_world_points)} figure_world_points, sample_side={self.sample_side}")

        # 打印相邻样品的边界索引，检查是否共享
        for i in range(len(self.sample_rects) - 1):
            rect1 = self.sample_rects[i]
            rect2 = self.sample_rects[i + 1]
            print(f"[DEBUG] 相邻样品 {rect1.sample_id}(idx={rect1.start_idx}~{rect1.end_idx}) 和 {rect2.sample_id}(idx={rect2.start_idx}~{rect2.end_idx})")

        # 第一步：收集所有样品边界点的索引和位置
        # 边界点 = 每个样品的起点和终点
        boundary_indices = set()
        for rect in self.sample_rects:
            if rect.start_idx >= 0:
                boundary_indices.add(rect.start_idx)
            if rect.end_idx >= 0:
                boundary_indices.add(rect.end_idx)
        boundary_indices = sorted(list(boundary_indices))

        # 第二步：预计算每个边界点处的垂线方向
        # 垂线方向基于该点处探槽轨迹的切线方向
        boundary_perps = {}  # idx -> (perp_x, perp_y) 归一化的垂线向量
        for idx in boundary_indices:
            if idx >= len(self.figure_world_points):
                continue
            p = self.figure_world_points[idx]

            # 计算该点处的切线方向
            if idx == 0:
                next_p = self.figure_world_points[idx + 1]
                dx = next_p[0] - p[0]
                dy = next_p[1] - p[1]
            elif idx == len(self.figure_world_points) - 1:
                prev_p = self.figure_world_points[idx - 1]
                dx = p[0] - prev_p[0]
                dy = p[1] - prev_p[1]
            else:
                prev_p = self.figure_world_points[idx - 1]
                next_p = self.figure_world_points[idx + 1]
                # 使用前后两点的平均方向
                dx = next_p[0] - prev_p[0]
                dy = next_p[1] - prev_p[1]

            seg_len = math.sqrt(dx * dx + dy * dy)
            if seg_len < 0.001:
                continue

            # 归一化切线
            dx /= seg_len
            dy /= seg_len

            # 垂线方向：perp = (-dy, dx)，然后根据sample_side调整方向
            perp_x = -dy * self.sample_side
            perp_y = dx * self.sample_side
            perp_len = math.sqrt(perp_x * perp_x + perp_y * perp_y)
            if perp_len > 0.001:
                perp_x /= perp_len
                perp_y /= perp_len
                boundary_perps[idx] = (perp_x, perp_y)

        print(f"[DEBUG] _draw_sample_areas: {len(boundary_perps)} boundary perpendiculars calculated")

        # 第三步：绘制每个样品矩形，使用共用的边界垂线
        for idx, rect in enumerate(self.sample_rects):
            # 获取样品段的起止索引
            start_idx = rect.start_idx if rect.start_idx >= 0 else 0
            end_idx = rect.end_idx if rect.end_idx >= 0 else start_idx

            # 确保索引有效
            if start_idx >= len(self.figure_world_points) or end_idx >= len(self.figure_world_points):
                print(f"[DEBUG] Sample {rect.sample_id}: invalid indices start={start_idx}, end={end_idx}")
                continue

            # 提取样品段的所有节点
            segment_points = self.figure_world_points[start_idx:end_idx + 1]

            if len(segment_points) < 2:
                print(f"[DEBUG] Sample {rect.sample_id}: segment too short, only {len(segment_points)} points")
                continue

            print(f"[DEBUG] Sample {rect.sample_id}: segment from idx {start_idx} to {end_idx}, {len(segment_points)} points")

            # 生成原线段点和偏移线点
            original_points = []  # 原线段上的点
            offset_points = []    # 偏移后的点

            for i, (px, py) in enumerate(segment_points):
                # 计算该节点处的切线方向
                if i < len(segment_points) - 1:
                    next_pt = segment_points[i + 1]
                    trench_dx = next_pt[0] - px
                    trench_dy = next_pt[1] - py
                elif i > 0:
                    prev_pt = segment_points[i - 1]
                    trench_dx = px - prev_pt[0]
                    trench_dy = py - prev_pt[1]
                else:
                    trench_dx, trench_dy = 1.0, 0.0

                # 归一化切线方向
                trench_len = math.sqrt(trench_dx * trench_dx + trench_dy * trench_dy)
                if trench_len < 0.001:
                    trench_dx, trench_dy = 1.0, 0.0
                    trench_len = 1.0
                trench_dx /= trench_len
                trench_dy /= trench_len

                # 左手边法向量 = (-dy, dx)
                perp_x = -trench_dy
                perp_y = trench_dx

                # 添加原线段点
                original_points.append((px, py))

                # 检查是否是边界点，如果是，使用预计算的共用垂线
                # 注意：boundary_perps已经乘过sample_side了
                current_idx = start_idx + i
                if current_idx in boundary_perps:
                    perp_x, perp_y = boundary_perps[current_idx]
                    # boundary_perps已经包含sample_side，不需要再乘
                    offset_px = px + perp_x * self.thickness_m
                    offset_py = py + perp_y * self.thickness_m
                else:
                    # 非边界点，使用当前计算的perp（需要乘以sample_side）
                    # perp = (-trench_dy * sample_side, trench_dx * sample_side)
                    perp_x = -trench_dy * self.sample_side
                    perp_y = trench_dx * self.sample_side
                    offset_px = px + perp_x * self.thickness_m
                    offset_py = py + perp_y * self.thickness_m
                offset_points.append((offset_px, offset_py))

            # 生成闭合多边形：原线段 + 偏移线（反向）首尾闭合
            polygon_points = []

            # 原线段点（正向）
            for pt in original_points:
                sp = self._to_screen(pt[0], pt[1])
                polygon_points.append(QPoint(int(sp.x()), int(sp.y())))

            # 偏移线点（反向），首尾闭合所以从 end_idx 到 start_idx
            for pt in reversed(offset_points):
                sp = self._to_screen(pt[0], pt[1])
                polygon_points.append(QPoint(int(sp.x()), int(sp.y())))

            # 设置填充颜色
            color_idx = min(rect.color_index, len(self.colors) - 1)
            fill_color = self.colors[color_idx]
            painter.setBrush(fill_color)
            painter.setPen(self.border_pen)

            # 绘制多边形
            polygon = QPolygon(polygon_points)
            painter.drawPolygon(polygon)


    def _draw_labels(self, painter: QPainter):
        """绘制样品号标注（使用世界坐标）"""
        painter.setPen(self.text_pen)
        font = QFont("Microsoft YaHei", 9)
        painter.setFont(font)

        for idx, rect in enumerate(self.sample_rects):
            # 标注位置在样品矩形外侧（中点 + 厚度偏移）
            # sample_rects 已经使用投影表小坐标，不需要加 start_x/start_y
            mid_x = (rect.x_start + rect.x_end) / 2
            mid_y = (rect.y_start + rect.y_end) / 2

            # 获取前后样品
            prev_mid_x, prev_mid_y = None, None
            next_mid_x, next_mid_y = None, None

            if idx > 0:
                prev_rect = self.sample_rects[idx - 1]
                prev_mid_x = (prev_rect.x_start + prev_rect.x_end) / 2
                prev_mid_y = (prev_rect.y_start + prev_rect.y_end) / 2

            if idx < len(self.sample_rects) - 1:
                next_rect = self.sample_rects[idx + 1]
                next_mid_x = (next_rect.x_start + next_rect.x_end) / 2
                next_mid_y = (next_rect.y_start + next_rect.y_end) / 2

            # 计算探槽方向向量
            if prev_mid_x is not None and next_mid_x is not None:
                trench_dx = next_mid_x - prev_mid_x
                trench_dy = next_mid_y - prev_mid_y
            elif prev_mid_x is not None:
                trench_dx = mid_x - prev_mid_x
                trench_dy = mid_y - prev_mid_y
            elif next_mid_x is not None:
                trench_dx = next_mid_x - mid_x
                trench_dy = next_mid_y - mid_y
            else:
                trench_dx = rect.x_end - rect.x_start
                trench_dy = rect.y_end - rect.y_start

            trench_len = math.sqrt(trench_dx * trench_dx + trench_dy * trench_dy)
            if trench_len < 0.001:
                trench_dx, trench_dy = 1.0, 0.0
                trench_len = 1.0
            trench_dx /= trench_len
            trench_dy /= trench_len

            # 垂直方向
            perp_x = -trench_dy
            perp_y = trench_dx

            # 标签偏移
            label_offset = self.sample_side * self.thickness_m * 1.5
            label_x = mid_x + perp_x * label_offset
            label_y = mid_y + perp_y * label_offset

            p = self._to_screen(label_x, label_y)
            painter.drawText(int(p.x()) - 15, int(p.y()), rect.sample_id)

    def _draw_scale_bar(self, painter: QPainter):
        """绘制比例尺（动态显示实际米数）"""
        painter.setPen(QPen(QColor(0, 0, 0), 2))

        # 在左下角绘制比例尺
        bar_length_px = 50  # 像素长度
        bar_x = 20
        bar_y = self.height() - 30

        # 计算50像素代表的图面距离，再换算为实际米数
        # figure_world_points已经是按scale_factor缩放过的
        # 屏幕像素 / self._scale = 图面距离
        # 图面距离 / self.scale_factor = 实际米数
        figure_distance = bar_length_px / self._scale if self._scale != 0 else 0
        real_meters = figure_distance / self.scale_factor if self.scale_factor != 0 else 0

        # 绘制比例尺条
        painter.drawLine(int(bar_x), int(bar_y), int(bar_x + bar_length_px), int(bar_y))
        painter.drawLine(int(bar_x), int(bar_y), int(bar_x), int(bar_y - 5))
        painter.drawLine(int(bar_x + bar_length_px), int(bar_y), int(bar_x + bar_length_px), int(bar_y - 5))

        # 绘制文字
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        font = QFont("Microsoft YaHei", 8)
        painter.setFont(font)
        painter.drawText(int(bar_x), int(bar_y - 10), "0")
        painter.drawText(int(bar_x + bar_length_px - 10), int(bar_y - 10), f"{real_meters:.0f}m")

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件"""
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
            self._drag_start_center = QPointF(self._center_x, self._center_y)

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件（拖拽平移 + 坐标显示）"""
        # 更新鼠标世界坐标
        self._mouse_x, self._mouse_y = self._to_world(event.x(), event.y())
        self.mouse_moved.emit(self._mouse_x, self._mouse_y)

        # 拖拽平移（通过调整center实现）
        if hasattr(self, '_drag_start') and event.buttons() == Qt.LeftButton:
            delta = event.pos() - self._drag_start
            # 将屏幕差值转换为世界坐标差值（取反实现正确拖拽方向）
            delta_world_x = -delta.x() / self._scale
            delta_world_y = delta.y() / self._scale
            self._center_x = self._drag_start_center.x() + delta_world_x
            self._center_y = self._drag_start_center.y() + delta_world_y
            self.update()
        else:
            # 非拖拽时只更新坐标显示
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件"""
        if event.button() == Qt.LeftButton:
            self.view_changed.emit()

    def resizeEvent(self, event: QResizeEvent):
        """窗口大小改变事件"""
        # 调用父类方法
        super().resizeEvent(event)

        # 如果有数据，重新计算缩放比例
        if self.trench_length > 0:
            print(f"[Preview] resizeEvent: new size {event.size().width()}x{event.size().height()}")
            self._recalculate_scale()
            self.update()

    def wheelEvent(self, event: QWheelEvent):
        """滚轮缩放（以鼠标位置为中心）"""
        # 获取鼠标位置的世界坐标
        mouse_world_x, mouse_world_y = self._to_world(event.x(), event.y())

        # 计算缩放因子
        if event.angleDelta().y() > 0:
            # 放大
            new_scale = self._scale * 1.1
        else:
            # 缩小
            new_scale = self._scale / 1.1

        # 限制缩放范围（最大50倍）
        new_scale = max(0.1, min(50.0, new_scale))

        # 计算新的center，使鼠标位置保持不变（zoom towards mouse）
        scale_ratio = new_scale / self._scale
        new_center_x = mouse_world_x - (mouse_world_x - self._center_x) / scale_ratio
        new_center_y = mouse_world_y - (mouse_world_y - self._center_y) / scale_ratio

        # 更新缩放和中心
        self._scale = new_scale
        self._center_x = new_center_x
        self._center_y = new_center_y

        self.view_changed.emit()
        self.update()

    def contextMenuEvent(self, event):
        """右键菜单"""
        menu = QMenu(self)

        reset_action = menu.addAction("重置视图")
        reset_action.triggered.connect(self.reset_view)

        menu.exec_(event.globalPos())
