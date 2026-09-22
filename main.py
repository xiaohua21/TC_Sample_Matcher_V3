# -*- coding: utf-8 -*-
"""
TC_Sample_Matcher V3.0
探槽样品区可视化与DXF导出工具

功能：
- 读取采样表及探槽基本特征表Excel数据
- 复用V2计算逻辑生成样轨投影数据
- 可视化预览探槽剖面图
- 支持设置样品厚度、比例尺
- 支持设置样品在左侧或右侧
- 支持设置探槽起点坐标（自动从0号基点提取）
- 支持样品号标注
- 导出DXF文件

作者：消化
"""

import os
import sys
from typing import List, Dict, Any, Optional, Tuple

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QPushButton, QLabel, QLineEdit,
    QFileDialog, QMessageBox, QTextEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QStatusBar, QMenuBar, QMenu, QAction,
    QDialog, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from src.core import (
    read_sample_table, read_tc_feature_table,
    generate_sample_track_projection, get_tc_start_coords,
    get_available_tcs, generate_all_projection_tables
)
from src.tc_dxf.dxf_writer import TCDXFWriter, SampleArea
from src.tc_dxf.preview_widget import PreviewWidget, SampleRect
from src.tc_dxf.dxf_mover import DXFMover


STYLE_SHEET = """
QMainWindow {
    background-color: #f5f7fa;
}

QGroupBox {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
    font-size: 13px;
    font-weight: bold;
    color: #2c3e50;
    border: 2px solid #dcdde1;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    background-color: white;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 8px;
    color: #3498db;
}

QLabel {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
    font-size: 12px;
    font-weight: bold;
    color: #2c3e50;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
    border: 1px solid #bdc3c7;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
    background: white;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #3498db;
}

QPushButton {
    font-family: 'SimHei', 'Microsoft YaHei', sans-serif;
    min-height: 36px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    background-color: #3498db;
    color: white;
}
QPushButton:hover {
    background-color: #2980b9;
}
QPushButton:pressed {
    background-color: #2471a3;
}
QPushButton:disabled {
    background-color: #bdc3c7;
    color: #7f8c8d;
}

QPushButton#open_btn {
    background-color: #27ae60;
}
QPushButton#open_btn:hover {
    background-color: #229954;
}

QPushButton#export_btn {
    background-color: #e74c3c;
}
QPushButton#export_btn:hover {
    background-color: #c0392b;
}

QTextEdit {
    background-color: #2c3e50;
    color: #ecf0f1;
    border: 1px solid #34495e;
    border-radius: 6px;
    font-family: 'SimHei', 'Microsoft YaHei', monospace;
    font-size: 12px;
    padding: 8px;
}

QStatusBar {
    background-color: #ecf0f1;
    color: #7f8c8d;
    border-top: 1px solid #dcdde1;
}
"""


# 默认比例尺（输入Excel中坐标是1:1000）
DEFAULT_INPUT_SCALE = 1000


class DXFGenerator(QThread):
    """DXF生成线程"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, output_path: str, projection_data: List[Dict[str, Any]],
                 trench_id: str, azimuth: float, sample_thickness: float,
                 scale: int, sample_side: int, start_x: float, start_y: float,
                 segments: List[Tuple[float, float]] = None, input_scale: int = 1000,
                 move_offset_x: float = 0.0, move_offset_y: float = 0.0,
                 world_points: List[Tuple[float, float]] = None,
                 sample_rects: List = None,
                 wall_offset: float = 5.0, show_walls: bool = True,
                 cd_points: List = None,
                 boundary_perps: Dict = None):
        super().__init__()
        self.output_path = output_path
        self.projection_data = projection_data
        self.trench_id = trench_id
        self.azimuth = azimuth
        self.sample_thickness = sample_thickness
        self.scale = scale
        self.sample_side = sample_side
        self.start_x = start_x
        self.start_y = start_y
        self.segments = segments or []
        self.input_scale = input_scale
        self.move_offset_x = move_offset_x
        self.move_offset_y = move_offset_y
        self.world_points = world_points  # 直接使用传入的world_points
        self.sample_rects = sample_rects   # 样品矩形列表
        self.wall_offset = wall_offset  # 探槽壁偏移距离
        self.show_walls = show_walls    # 是否绘制探槽壁
        self.cd_points = cd_points      # CD线坐标（来自Preview）
        self.boundary_perps = boundary_perps  # 边界垂线（来自Preview）

    def run(self):
        try:
            self.progress.emit(f"[DXF] scale={self.scale}, input_scale={self.input_scale}")
            self.progress.emit(f"[DXF] self.cd_points={len(self.cd_points) if self.cd_points else 0} points")
            self.progress.emit("正在生成DXF文件...")
            writer = TCDXFWriter()
            writer.trench_id = self.trench_id  # 用于set_world_points中创建trench_profile
            writer.set_params(self.sample_thickness, self.scale, self.sample_side, self.input_scale)
            writer.set_start_coords(self.start_x, self.start_y)

            # 设置探槽壁参数
            writer.wall_offset = self.wall_offset
            writer.show_walls = self.show_walls

            # 如果传入了world_points（已经移动后的），直接使用
            self.progress.emit(f"[DXF] DEBUG: self.world_points is None = {self.world_points is None}")
            if self.world_points is not None:
                self.progress.emit("[DXF] 调用set_world_points...")
                writer.set_world_points(self.world_points)
                self.progress.emit("[DXF] set_world_points完成")
                # 同时设置sample_rects
                if self.sample_rects is not None:
                    writer.set_sample_rects(self.sample_rects)
                # 同时设置cd_points（来自Preview的计算结果）
                self.progress.emit(f"[DXF] self.cd_points check: {self.cd_points is not None}, len={len(self.cd_points) if self.cd_points else 0}")
                if self.cd_points is not None and len(self.cd_points) > 0:
                    writer.set_cd_points(self.cd_points)
                    self.progress.emit(f"[DXF] set_cd_points called with {len(self.cd_points)} points")
                # 设置boundary_perps（来自Preview的计算结果）
                if self.boundary_perps is not None and len(self.boundary_perps) > 0:
                    writer.set_boundary_perps(self.boundary_perps)
                    self.progress.emit(f"[DXF] set_boundary_perps called with {len(self.boundary_perps)} perps")
                self.progress.emit(f"[DXF] 使用已移动的world_points和sample_rects")
            else:
                # 否则从projection_data加载
                writer.load_from_projection_data(self.trench_id, self.projection_data,
                                               self.azimuth, self.segments)

            writer.write_dxf_file(self.output_path)
            self.finished.emit(self.output_path)
        except Exception as e:
            import traceback
            print(f"[DXF Worker] Error: {e}")
            print(traceback.format_exc())
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("探槽样品区智能投影软件  作者：消化")
        self.setMinimumSize(1200, 900)
        self.setStyleSheet(STYLE_SHEET)

        # 数据
        self.input_file_path: Optional[str] = None
        self.sample_df = None  # 采样表DataFrame
        self.feature_data = {}  # 探槽特征数据
        self.available_tcs = []  # 可用探槽列表
        self.current_tc_id: Optional[str] = None
        self.current_projection_data: List[Dict[str, Any]] = []
        self.current_azimuth: float = 0.0
        self.current_segments: List[Tuple[float, float]] = []  # 探槽段列表
        self.input_scale = DEFAULT_INPUT_SCALE  # 输入Excel中坐标的比例尺

        self.init_ui()
        self.create_menu()

    def init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局：垂直（上层：左右面板，下层：日志）
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        central_widget.setLayout(main_layout)

        # 上层：左右水平布局
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)

        # 左侧控制面板（设置固定宽度）
        left_panel = self._create_control_panel()
        left_panel.setFixedWidth(420)
        top_layout.addWidget(left_panel, 1)  # stretch = 1

        # 右侧预览区
        right_panel = self._create_preview_panel()
        top_layout.addWidget(right_panel, 2)  # stretch = 2，右侧更宽
        main_layout.addLayout(top_layout, 1)

        # 下层：日志区
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(5, 5, 5, 5)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(100)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        # 状态栏
        self.statusBar().showMessage("就绪")

    def _create_control_panel(self) -> QWidget:
        """创建左侧控制面板"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setSpacing(15)
        content.setLayout(content_layout)

        # 文件选择区
        file_group = QGroupBox("数据文件")
        file_layout = QVBoxLayout()

        self.file_label = QLabel("尚未选择文件")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("""
            QLabel {
                background-color: #ecf0f1;
                padding: 8px;
                border-radius: 4px;
                color: #7f8c8d;
            }
        """)
        file_layout.addWidget(self.file_label)

        self.open_btn = QPushButton("打开Excel")
        self.open_btn.setObjectName("open_btn")
        self.open_btn.clicked.connect(self.open_file)
        file_layout.addWidget(self.open_btn)

        file_group.setLayout(file_layout)
        content_layout.addWidget(file_group)

        # 探槽选择区
        tc_group = QGroupBox("探槽选择")
        tc_layout = QVBoxLayout()

        self.tc_combo = QComboBox()
        self.tc_combo.currentIndexChanged.connect(self.on_tc_changed)
        tc_layout.addWidget(QLabel("选择探槽:"))
        tc_layout.addWidget(self.tc_combo)

        self.select_all_check = QCheckBox("全选导出全部探槽")
        self.select_all_check.setChecked(False)
        self.select_all_check.stateChanged.connect(self.on_select_all_changed)
        tc_layout.addWidget(self.select_all_check)

        tc_group.setLayout(tc_layout)
        content_layout.addWidget(tc_group)

        # 参数设置区
        params_group = QGroupBox("参数设置")
        params_layout = QGridLayout()

        # 比例尺（输出）
        params_layout.addWidget(QLabel("输出比例尺:"), 0, 0)
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(100, 10000)
        self.scale_spin.setValue(1000)
        self.scale_spin.valueChanged.connect(self.on_scale_changed)
        params_layout.addWidget(self.scale_spin, 0, 1)

        # 样品厚度
        params_layout.addWidget(QLabel("样品厚度(mm):"), 1, 0)
        self.thickness_spin = QDoubleSpinBox()
        self.thickness_spin.setRange(0.1, 100)
        self.thickness_spin.setValue(1.0)
        self.thickness_spin.setSuffix(" mm")
        self.thickness_spin.setDecimals(1)
        self.thickness_spin.setSingleStep(0.1)
        self.thickness_spin.valueChanged.connect(self.update_preview)
        params_layout.addWidget(self.thickness_spin, 1, 1)

        # 样品位置
        params_layout.addWidget(QLabel("样品位置:"), 2, 0)
        self.side_combo = QComboBox()
        self.side_combo.addItem("左侧", -1)
        self.side_combo.addItem("右侧", 1)
        self.side_combo.setCurrentIndex(1)  # 默认右侧
        self.side_combo.currentIndexChanged.connect(self.update_preview)
        params_layout.addWidget(self.side_combo, 2, 1)

        # 起点坐标（只读，自动从Excel提取）
        params_layout.addWidget(QLabel("起点X:"), 3, 0)
        self.start_x_edit = QLineEdit()
        self.start_x_edit.setReadOnly(True)
        self.start_x_edit.setStyleSheet("background-color: #ecf0f1;")
        params_layout.addWidget(self.start_x_edit, 3, 1)

        params_layout.addWidget(QLabel("起点Y:"), 4, 0)
        self.start_y_edit = QLineEdit()
        self.start_y_edit.setReadOnly(True)
        self.start_y_edit.setStyleSheet("background-color: #ecf0f1;")
        params_layout.addWidget(self.start_y_edit, 4, 1)

        # 坐标换算说明
        coord_note = QLabel("注：起点坐标已按输出比例尺换算")
        coord_note.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        params_layout.addWidget(coord_note, 5, 0, 1, 2)

        # 显示标注
        self.show_labels_check = QCheckBox("显示样品号标注")
        self.show_labels_check.setChecked(True)
        self.show_labels_check.stateChanged.connect(self.update_preview)
        params_layout.addWidget(self.show_labels_check, 6, 0, 1, 2)

        # 探槽壁偏移距离
        params_layout.addWidget(QLabel("探槽壁偏移(mm):"), 7, 0)
        self.wall_offset_spin = QDoubleSpinBox()
        self.wall_offset_spin.setRange(0.1, 100)
        self.wall_offset_spin.setValue(2.0)
        self.wall_offset_spin.setSuffix(" mm")
        self.wall_offset_spin.setDecimals(1)
        self.wall_offset_spin.setSingleStep(0.5)
        self.wall_offset_spin.valueChanged.connect(self.update_preview)
        params_layout.addWidget(self.wall_offset_spin, 7, 1)

        # 绘制探槽壁复选框
        self.show_walls_check = QCheckBox("绘制探槽壁轮廓")
        self.show_walls_check.setChecked(True)
        self.show_walls_check.stateChanged.connect(self.update_preview)
        params_layout.addWidget(self.show_walls_check, 8, 0, 1, 2)

        params_group.setLayout(params_layout)
        content_layout.addWidget(params_group)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

        return widget

    def _create_preview_panel(self) -> QWidget:
        """创建右侧预览面板"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 5, 0, 0)  # 减小上边距
        layout.setSpacing(5)
        widget.setLayout(layout)

        # 标题（紧凑设计）
        title = QLabel("探槽平面图预览")
        title.setFont(QFont("SimHei", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50; padding: 5px; background: #f0f0f0;")
        title.setFixedHeight(30)
        layout.addWidget(title)

        # 预览控件（使用Expanding策略填充空间）
        self.preview_widget = PreviewWidget()
        size_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_widget.setSizePolicy(size_policy)
        # 连接鼠标坐标信号到状态栏
        self.preview_widget.mouse_moved.connect(self.on_mouse_moved)
        layout.addWidget(self.preview_widget, 1)  # stretch factor = 1

        # 导出按钮（单独放置在预览下方）
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.export_projection_btn = QPushButton("导出投影表")
        self.export_projection_btn.setObjectName("export_projection_btn")
        self.export_projection_btn.setEnabled(False)
        self.export_projection_btn.clicked.connect(self.export_projection_table)
        self.export_projection_btn.setStyleSheet("""
            QPushButton {
                min-height: 36px;
                font-size: 13px;
                background-color: #27AE60;
                color: white;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #1E8449; }
            QPushButton:disabled { background-color: #C7C7CC; }
        """)

        self.export_btn = QPushButton("导出DXF")
        self.export_btn.setObjectName("export_btn")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_dxf)
        self.export_btn.setStyleSheet("""
            QPushButton {
                min-height: 36px;
                font-size: 13px;
                background-color: #007AFF;
                color: white;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #0051D5; }
            QPushButton:disabled { background-color: #C7C7CC; }
        """)

        btn_layout.addWidget(self.export_projection_btn)
        btn_layout.addWidget(self.export_btn)

        # 添加整体移动按钮
        self.move_btn = QPushButton("整体移动（先导出DXF）")
        self.move_btn.setObjectName("move_btn")
        self.move_btn.setEnabled(False)  # 导出DXF后才启用
        self.move_btn.clicked.connect(self.on_move_dxf)
        self.move_btn.setStyleSheet("""
            QPushButton {
                min-height: 36px;
                font-size: 13px;
                background-color: #CCCCCC;
                color: #888888;
                border-radius: 6px;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #888888;
            }
        """)
        btn_layout.addWidget(self.move_btn)

        layout.addLayout(btn_layout)

        return widget

    def create_menu(self):
        """创建菜单"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件")

        open_action = QAction("打开Excel", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        export_projection_action = QAction("导出投影表", self)
        export_projection_action.setShortcut("Ctrl+E")
        export_projection_action.triggered.connect(self.export_projection_table)
        file_menu.addAction(export_projection_action)

        export_action = QAction("导出DXF", self)
        export_action.setShortcut("Ctrl+S")
        export_action.triggered.connect(self.export_dxf)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助")

        help_action = QAction("使用说明", self)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)

        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def open_file(self):
        """打开Excel文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择采样表及探槽基本特征表", "",
            "Excel文件 (*.xlsx *.xls)"
        )

        if not path:
            return

        try:
            self.input_file_path = path

            # 读取采样表和探槽特征表
            self.sample_df = read_sample_table(path)
            self.feature_data = read_tc_feature_table(path)

            # 获取可用探槽列表
            self.available_tcs = get_available_tcs(self.sample_df)

            if not self.available_tcs:
                QMessageBox.warning(self, "错误", "未找到有效的探槽数据")
                return

            # 更新UI
            basename = os.path.basename(path)
            self.file_label.setText(basename)
            self.file_label.setStyleSheet("""
                QLabel {
                    background-color: #e8f8f5;
                    padding: 8px;
                    border-radius: 4px;
                    color: #27ae60;
                    border: 1px solid #27ae60;
                }
            """)

            # 更新探槽下拉框
            self.tc_combo.blockSignals(True)
            self.tc_combo.clear()
            for tc_id in self.available_tcs:
                self.tc_combo.addItem(tc_id)
            self.tc_combo.blockSignals(False)

            # 不自动选择，让用户自己选择
            # if self.available_tcs:
            #     self.tc_combo.setCurrentIndex(0)

            self.log_text.append(f"已加载: {basename}")
            self.log_text.append(f"发现 {len(self.available_tcs)} 个探槽: {', '.join(self.available_tcs)}")
            self.log_text.append("请选择探槽后查看预览")
            self.log_text.append("-" * 40)

            self.statusBar().showMessage(f"已加载: {basename}")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取文件失败:\n{str(e)}")
            self.log_text.append(f"错误: {str(e)}")

    def on_tc_changed(self, index):
        """探槽选择改变"""
        self.log_text.append(f"=== 切换探槽 ===")
        self.log_text.append(f"[选择] index={index}")

        # 忽略无效索引
        if index < 0:
            return

        # 确保数据已加载
        if self.sample_df is None or not self.feature_data:
            self.log_text.append(f"[错误] 数据未加载")
            return

        if index >= len(self.available_tcs):
            return

        tc_id = self.available_tcs[index]
        self.log_text.append(f"[选择] tc_id={tc_id}")
        self.current_tc_id = tc_id

        try:
            # 生成样轨投影数据
            projection_data = generate_sample_track_projection(
                tc_id, self.sample_df, self.feature_data
            )
            self.current_projection_data = projection_data

            # 获取方位角（从第一行数据）
            if self.current_projection_data:
                self.current_azimuth = self.current_projection_data[0].get('方位', 0)
            else:
                self.current_azimuth = 0.0

            # 获取起点坐标（0号基点的XY）
            raw_start_x, raw_start_y = get_tc_start_coords(self.feature_data, tc_id)

            # 坐标换算：从输入比例尺换算到输出比例尺
            # 比例尺换算公式：新坐标 = 原坐标 × (原比例尺 / 新比例尺)
            # 例如 1:1000 -> 1:500，新坐标 = 原坐标 × (1000/500) = 原坐标 × 2
            output_scale = self.scale_spin.value()
            scale_ratio = self.input_scale / output_scale

            start_x = raw_start_x * scale_ratio
            start_y = raw_start_y * scale_ratio

            # 更新界面
            self.start_x_edit.setText(f"{start_x:.2f}")
            self.start_y_edit.setText(f"{start_y:.2f}")

            # 更新日志
            self.log_text.append(f"已加载探槽: {tc_id}")
            self.log_text.append(f"  起点坐标: ({raw_start_x:.2f}, {raw_start_y:.2f}) @ 1:{self.input_scale}")
            self.log_text.append(f"  换算后: ({start_x:.2f}, {start_y:.2f}) @ 1:{output_scale}")

            # 启用导出按钮
            self.export_btn.setEnabled(True)
            self.export_projection_btn.setEnabled(True)

            # 重置移动标志，切换探槽后需要重新计算world_points
            self.preview_widget._moved = False

            # 更新预览
            self.update_preview()

            self.statusBar().showMessage(f"已加载: {tc_id}")

        except Exception as e:
            import traceback
            error_msg = f"计算错误: {str(e)}\n\n{traceback.format_exc()}"
            print(error_msg)  # 打印到控制台
            self.log_text.append(f"计算错误: {str(e)}")
            self.log_text.append(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"计算投影数据失败:\n{str(e)}")

    def on_select_all_changed(self, state):
        """全选复选框状态改变"""
        if state:
            self.log_text.append("已切换到全选模式：导出全部探槽")
        else:
            self.log_text.append("已切换到单选模式：导出当前探槽")

    def on_scale_changed(self, value):
        """比例尺改变，重新计算起点坐标"""
        self.log_text.append(f"=== 修改比例尺 ===")
        self.log_text.append(f"[比例尺] 新比例尺=1:{value}")
        self.log_text.append(f"[比例尺] input_scale={self.input_scale}")
        if not self.current_tc_id:
            return

        # 重新获取原始坐标并换算
        raw_start_x, raw_start_y = get_tc_start_coords(self.feature_data, self.current_tc_id)
        scale_ratio = self.input_scale / value
        start_x = raw_start_x * scale_ratio
        start_y = raw_start_y * scale_ratio

        self.log_text.append(f"[比例尺] 原始起点=({raw_start_x}, {raw_start_y})")
        self.log_text.append(f"[比例尺] 换算后起点=({start_x}, {start_y})")

        self.start_x_edit.setText(f"{start_x:.2f}")
        self.start_y_edit.setText(f"{start_y:.2f}")

        # 调用preview_widget的set_output_scale来重新计算figure_world_points
        # 这会基于real_world_points重新应用scale_factor和保留move_delta
        self.preview_widget.set_output_scale(value)

    def update_preview(self):
        """更新预览"""
        self.log_text.append(f"[预览] 更新预览")
        self.log_text.append(f"[预览] projection_data数量={len(self.current_projection_data) if self.current_projection_data else 0}")

        if not self.current_projection_data:
            self.log_text.append(f"[预览] 无投影数据，返回")
            return

        # 获取参数
        scale = self.scale_spin.value()
        thickness_mm = self.thickness_spin.value()
        sample_side = self.side_combo.currentData()

        self.log_text.append(f"[预览] 比例尺=1:{scale}, 厚度={thickness_mm}mm, 位置= {'左侧' if sample_side == -1 else '右侧'}")

        # 计算样品数量
        h_samples = [d for d in self.current_projection_data
                    if str(d.get('样号', '')).startswith('H')]
        sample_count = len(h_samples)

        # 计算样品厚度（用户输入值直接作为DXF中的厚度值）
        thickness_m = thickness_mm
        self.log_text.append(f"[预览] 实际厚度={thickness_m}m")

        # 获取起点坐标
        raw_start_x, raw_start_y = get_tc_start_coords(self.feature_data, self.current_tc_id)

        # 坐标换算：从输入比例尺换算到输出比例尺
        output_scale = self.scale_spin.value()
        scale_ratio = self.input_scale / output_scale
        start_x = raw_start_x * scale_ratio
        start_y = raw_start_y * scale_ratio

        # 获取起始方位角（第一段的方位角）
        start_azimuth = 0.0
        segments = []  # 探槽段列表
        total_length = 0.0  # 探槽总长度
        if self.current_tc_id in self.feature_data:
            features = self.feature_data[self.current_tc_id]
            if len(features) >= 2:
                start_azimuth = features[1].get('azimuth', 0.0)
                # 构建段列表（直接使用导线长度，假设已经是水平距离）
                for i in range(1, len(features)):
                    azimuth = features[i].get('azimuth', 0.0)
                    length = features[i].get('length', 0.0)  # 假设已是水平距离
                    if length > 0:
                        segments.append((azimuth, length))
                        total_length += length  # 累加水平距离作为总长度

        self.log_text.append(f"[预览] 起点=({start_x:.2f}, {start_y:.2f}), 方位角={start_azimuth}")
        self.log_text.append(f"[预览] 段数={len(segments)}, 总长度={total_length:.2f}")

        # 调试：打印投影表数据
        print(f"[DEBUG] current_projection_data ({len(self.current_projection_data)} rows):")
        for idx, row in enumerate(self.current_projection_data[:10]):
            sample_id = str(row.get('样号', '')).strip()
            x = row.get('X', 0) or 0
            sample_length = row.get('样长', 0) or 0
            print(f"  [{idx}] 样号={sample_id}, X={x}, 样长={sample_length}")

        # 投影表最后一行X值
        if self.current_projection_data:
            last_x = self.current_projection_data[-1].get('X', 0) or 0
            print(f"[DEBUG] 投影表最后一行X的绝对值 = abs({last_x}) = {abs(last_x):.2f}")
            print(f"[DEBUG] 对比: segments总长={sum(L for az,L in segments):.2f}, 投影表X绝对值={abs(last_x):.2f}, 差异={abs(last_x) - sum(L for az,L in segments):.2f}")

        # 生成样品和非采样区矩形（使用投影表的世界坐标）
        # V2逻辑：直接使用投影表的X/Y作为世界坐标
        # X = 沿探槽方向的累积水平坐标（可能是负数，表示往回走）
        # Y = 垂直方向的累积坐标
        sample_rects = []
        i = 0
        for row in self.current_projection_data:
            sample_id = str(row.get('样号', '')).strip()

            # 世界坐标：直接使用投影表的X和Y作为终点
            x_end = row.get('X', 0) or 0
            y_end = row.get('Y', 0) or 0

            # 使用投影表的累计X/Y来计算起点
            # 投影表公式：X = cum_X + ∑X, Y = cum_Y + ∑Y
            # 其中 ∑X = 平距 * cos(方位差), ∑Y = 平距 * sin(方位差)
            sum_x = row.get('累计X', 0) or 0
            sum_y = row.get('累计Y', 0) or 0
            x_start = x_end - sum_x
            y_start = y_end - sum_y

            # 应用当前比例尺换算
            x_start = x_start * scale_ratio
            y_start = y_start * scale_ratio
            x_end = x_end * scale_ratio
            y_end = y_end * scale_ratio

            # 颜色索引：H样品用0/1交替，非采样区用2（灰色）
            if sample_id == '非采样区':
                color_index = 2  # 灰色表示非采样区
            elif sample_id.startswith('H'):
                color_index = i % 2
                i += 1
            else:
                continue

            sample_rects.append(SampleRect(x_start, y_start, x_end, y_end, sample_id, color_index))

        print(f"[update_preview] created {len(sample_rects)} rectangles (samples + non-samples)")

        # 更新预览控件（不要提前赋值sample_side，让set_data内部处理）
        self.preview_widget.show_labels = self.show_labels_check.isChecked()
        self.preview_widget.set_data(total_length, sample_rects, sample_side,
                                     start_x, start_y, start_azimuth, segments=segments,
                                     thickness_m=thickness_m,
                                     projection_data=self.current_projection_data,
                                     wall_offset=self.wall_offset_spin.value(),
                                     show_walls=self.show_walls_check.isChecked(),
                                     trench_id=self.current_tc_id,
                                     sample_count=sample_count)

        # 保存segments供DXF导出使用
        self.current_segments = segments

    def export_projection_table(self):
        """导出投影表Excel文件"""
        if not self.input_file_path:
            QMessageBox.warning(self, "警告", "请先打开Excel文件")
            return

        default_dir = os.path.join(os.path.dirname(self.input_file_path), 'output')
        if not os.path.exists(default_dir):
            os.makedirs(default_dir)

        try:
            self.statusBar().showMessage("正在生成投影表...")
            self.log_text.append(f"开始生成投影表...")
            self.log_text.append(f"  输入文件: {self.input_file_path}")

            if self.select_all_check.isChecked():
                # 全选：导出全部探槽
                selected_tcs = self.available_tcs
                count = len(selected_tcs)
                default_name = f"样轨投影表_全选{count}个.xlsx"
                default_path = os.path.join(default_dir, default_name)

                output_path, _ = QFileDialog.getSaveFileName(
                    self, "保存投影表", default_path,
                    "Excel文件 (*.xlsx)"
                )

                if not output_path:
                    return

                self.log_text.append(f"  模式: 导出全部探槽")
                self.log_text.append(f"  输出文件: {output_path}")

                all_results = generate_all_projection_tables(
                    self.input_file_path, output_path, selected_tcs=None  # None表示全部
                )

                if all_results:
                    self.log_text.append(f"  成功生成 {len(all_results)} 个探槽的投影表")
                    self.statusBar().showMessage("投影表生成完成")
                    QMessageBox.information(self, "完成", f"投影表已生成:\n{output_path}")
                else:
                    self.log_text.append("  错误: 未生成任何投影表")
                    self.statusBar().showMessage("投影表生成失败")
                    QMessageBox.warning(self, "警告", "未生成任何投影表")
            else:
                # 单选：只导出当前探槽
                current_tc = self.current_tc_id
                if not current_tc:
                    QMessageBox.warning(self, "警告", "请先选择一个探槽")
                    return

                default_name = f"样轨投影表_{current_tc}.xlsx"
                default_path = os.path.join(default_dir, default_name)

                output_path, _ = QFileDialog.getSaveFileName(
                    self, "保存投影表", default_path,
                    "Excel文件 (*.xlsx)"
                )

                if not output_path:
                    return

                self.log_text.append(f"  模式: 导出单个探槽 ({current_tc})")
                self.log_text.append(f"  输出文件: {output_path}")

                all_results = generate_all_projection_tables(
                    self.input_file_path, output_path, selected_tcs=[current_tc]
                )

                if all_results:
                    self.log_text.append(f"  成功生成 1 个探槽的投影表")
                    self.statusBar().showMessage("投影表生成完成")
                    QMessageBox.information(self, "完成", f"投影表已生成:\n{output_path}")
                else:
                    self.log_text.append("  错误: 未生成投影表")
                    self.statusBar().showMessage("投影表生成失败")
                    QMessageBox.warning(self, "警告", "未生成投影表")

        except Exception as e:
            import traceback
            self.log_text.append(f"  错误: {str(e)}")
            self.log_text.append(f"  详细: {traceback.format_exc()}")
            self.statusBar().showMessage("投影表生成失败")
            QMessageBox.critical(self, "错误", f"生成投影表失败:\n{str(e)}")

    def export_dxf(self):
        """导出DXF文件"""
        self.log_text.append(f"=== 导出DXF ===")
        if not self.current_projection_data:
            self.log_text.append(f"[导出] 无投影数据")
            return

        # 获取参数
        scale = self.scale_spin.value()
        thickness_mm = self.thickness_spin.value()
        sample_side = self.side_combo.currentData()
        start_x = float(self.start_x_edit.text()) if self.start_x_edit.text() else 0.0
        start_y = float(self.start_y_edit.text()) if self.start_y_edit.text() else 0.0

        # 计算样品厚度（用户输入值直接作为DXF中的厚度值）
        thickness_m = thickness_mm

        # 获取整体移动偏移量
        move_offset_x = getattr(self, 'move_offset_x', 0.0)
        move_offset_y = getattr(self, 'move_offset_y', 0.0)

        self.log_text.append(f"[导出] 探槽: {self.current_tc_id}")
        self.log_text.append(f"[导出] 比例尺: 1:{scale}")
        self.log_text.append(f"[导出] 样品厚度: {thickness_mm}mm")
        self.log_text.append(f"[导出] 样品位置: {'左侧' if sample_side == -1 else '右侧'}")
        self.log_text.append(f"[导出] 起点坐标: ({start_x}, {start_y})")
        self.log_text.append(f"[导出] 移动偏移: ({move_offset_x}, {move_offset_y})")

        # 如果current_segments为空，尝试从feature_data构建
        segments = self.current_segments
        if not segments and self.current_tc_id in self.feature_data:
            features = self.feature_data[self.current_tc_id]
            if len(features) >= 2:
                for i in range(1, len(features)):
                    azimuth = features[i].get('azimuth', 0.0)
                    length = features[i].get('length', 0.0)  # 假设已是水平距离
                    if length > 0:
                        segments.append((azimuth, length))
        print(f"[export_dxf] segments = {segments}")

        # 选择输出路径（默认放在output文件夹）
        default_name = f"{self.current_tc_id}_样品区.dxf"
        default_dir = os.path.join(os.path.dirname(self.input_file_path), 'output') if self.input_file_path else 'output'

        # 确保output文件夹存在
        if not os.path.exists(default_dir):
            os.makedirs(default_dir)

        default_path = os.path.join(default_dir, default_name)
        output_path, _ = QFileDialog.getSaveFileName(
            self, "保存DXF文件", default_path,
            "DXF文件 (*.dxf)"
        )

        if not output_path:
            return

        # 启动生成线程
        self.export_btn.setEnabled(False)
        self.statusBar().showMessage("正在生成DXF...")

        # 获取整体移动偏移量
        move_offset_x = getattr(self, 'move_offset_x', 0.0)
        move_offset_y = getattr(self, 'move_offset_y', 0.0)

        # 获取探槽壁参数
        wall_offset = self.wall_offset_spin.value()
        show_walls = self.show_walls_check.isChecked()

        # 获取PreviewWidget中的figure_world_points和sample_rects（用于DXF导出）
        # 注意：figure_world_points已经是图面坐标，不再需要scale_factor缩放
        preview_world_points = self.preview_widget.figure_world_points if hasattr(self.preview_widget, 'figure_world_points') else None
        preview_sample_rects = self.preview_widget.sample_rects if hasattr(self.preview_widget, 'sample_rects') else None
        preview_cd_points = self.preview_widget.cd_points if hasattr(self.preview_widget, 'cd_points') else None
        preview_boundary_perps = self.preview_widget.get_boundary_perps() if hasattr(self.preview_widget, 'get_boundary_perps') else None
        if preview_world_points:
            self.log_text.append(f"[导出] 使用预览中的figure_world_points: {len(preview_world_points)} 点")
            self.log_text.append(f"[导出] figure_world_points[0] = {preview_world_points[0] if preview_world_points else 'empty'}")
        if preview_sample_rects:
            self.log_text.append(f"[导出] 使用预览中的sample_rects: {len(preview_sample_rects)} 个")
        if preview_cd_points:
            self.log_text.append(f"[导出] 使用预览中的cd_points: {len(preview_cd_points)} 点")
        if preview_boundary_perps:
            self.log_text.append(f"[导出] 使用预览中的boundary_perps: {len(preview_boundary_perps)} 个")

        self.log_text.append(f"[导出] 探槽壁偏移: {wall_offset}m, 绘制探槽壁: {show_walls}")

        self.worker = DXFGenerator(
            output_path, self.current_projection_data, self.current_tc_id,
            self.current_azimuth, thickness_m, scale, sample_side,
            start_x, start_y, segments, self.input_scale,
            move_offset_x, move_offset_y,
            preview_world_points,
            preview_sample_rects,
            wall_offset, show_walls,
            preview_cd_points,
            preview_boundary_perps
        )
        self.worker.progress.connect(lambda msg: self.log_text.append(msg))
        self.worker.finished.connect(self.on_export_finished)
        self.worker.error.connect(self.on_export_error)
        self.worker.start()

    def on_export_finished(self, path: str):
        """导出完成"""
        self.export_btn.setEnabled(True)
        self.statusBar().showMessage("导出完成")
        self.log_text.append(f"导出成功: {path}")

        # 保存最后导出的DXF路径，启用整体移动按钮
        self.last_exported_dxf = path
        self.move_btn.setEnabled(True)
        self.move_btn.setText("整体移动")
        self.move_btn.setStyleSheet("""
            QPushButton {
                min-height: 36px;
                font-size: 13px;
                background-color: #FF9800;
                color: white;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #F57C00; }
            QPushButton:disabled { background-color: #C7C7CC; }
        """)
        self.log_text.append("DXF文件已导出，可以使用【整体移动】功能")
        QMessageBox.information(self, "完成", f"DXF文件已生成:\n{path}")

    def on_export_error(self, msg: str):
        """导出错误"""
        self.export_btn.setEnabled(True)
        self.statusBar().showMessage("导出失败")
        self.log_text.append(f"错误: {msg}")
        QMessageBox.critical(self, "错误", f"导出失败:\n{msg}")

    def on_move_dxf(self):
        """整体移动DXF文件

        流程：
        1. 检查是否有已导出的DXF文件
        2. 读取目标坐标（用户输入的起点X、Y）
        3. 使用DXFMover加载DXF并计算偏移量
        4. 保存移动后的DXF文件
        """
        self.log_text.append(f"=== 整体移动DXF ===")

        # 检查是否有已导出的DXF文件
        last_dxf = getattr(self, 'last_exported_dxf', None)
        if not last_dxf or not os.path.exists(last_dxf):
            QMessageBox.warning(self, "警告", "没有找到已导出的DXF文件，请先导出DXF")
            return

        # 获取目标坐标
        try:
            target_x = float(self.start_x_edit.text()) if self.start_x_edit.text() else 0.0
            target_y = float(self.start_y_edit.text()) if self.start_y_edit.text() else 0.0
        except ValueError:
            QMessageBox.warning(self, "警告", "起点坐标必须是有效的数字")
            return

        self.log_text.append(f"[整体移动] DXF文件: {last_dxf}")
        self.log_text.append(f"[整体移动] 目标坐标: ({target_x}, {target_y})")

        # 检查ezdxf库是否可用
        if not DXFMover.check_ezdxf():
            QMessageBox.warning(self, "警告",
                "需要安装ezdxf库才能使用整体移动功能\n"
                "请在命令行运行: pip install ezdxf")
            return

        try:
            # 创建移动器
            mover = DXFMover()

            # 加载DXF文件
            mover.load_dxf(last_dxf)

            # 计算偏移量（基于探槽起点）
            offset_x, offset_y = mover.calculate_offset(target_x, target_y)

            # 生成输出文件名
            input_dir = os.path.dirname(last_dxf)
            input_basename = os.path.basename(last_dxf)
            name_without_ext = os.path.splitext(input_basename)[0]
            output_name = f"{name_without_ext}_已移动.dxf"
            output_path = os.path.join(input_dir, output_name)

            self.log_text.append(f"[整体移动] 输出文件: {output_path}")

            # 执行移动
            mover.move_all(output_path, offset_x, offset_y)

            self.log_text.append(f"[整体移动] 完成！")
            self.statusBar().showMessage(f"整体移动完成: {output_path}")

            # 禁用移动按钮（避免重复移动）
            self.move_btn.setEnabled(False)
            self.move_btn.setText("整体移动（已完成）")
            self.move_btn.setStyleSheet("""
                QPushButton {
                    min-height: 36px;
                    font-size: 13px;
                    background-color: #CCCCCC;
                    color: #888888;
                    border-radius: 6px;
                }
            """)

            QMessageBox.information(self, "完成",
                f"DXF文件已整体移动到目标坐标\n\n"
                f"输出文件: {output_path}\n\n"
                f"偏移量: X={offset_x:.2f}, Y={offset_y:.2f}")

        except Exception as e:
            import traceback
            error_msg = f"整体移动失败: {str(e)}"
            self.log_text.append(f"[整体移动] 错误: {error_msg}")
            self.log_text.append(traceback.format_exc())
            QMessageBox.critical(self, "错误", error_msg)

    def on_mouse_moved(self, world_x: float, world_y: float):
        """鼠标移动时更新状态栏的世界坐标"""
        self.statusBar().showMessage(f"世界坐标: X={world_x:.2f}, Y={world_y:.2f}")

    def show_help(self):
        """显示帮助"""
        dialog = QDialog(self)
        dialog.setWindowTitle("使用说明")
        dialog.setMinimumSize(600, 500)

        layout = QVBoxLayout(dialog)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml("""
            <h2>探槽样品区智能投影软件</h2>
            <p><b>作者：</b>消化</p>

            <h3>功能介绍</h3>
            <ul>
            <li>读取采样表及探槽基本特征表Excel数据</li>
            <li>复用V2计算逻辑生成样轨投影数据</li>
            <li>可视化预览探槽剖面图</li>
            <li>导出AutoCAD DXF格式文件</li>
            </ul>

            <h3>使用步骤</h3>
            <ol>
            <li>点击【打开Excel】按钮，选择"采样表及探槽基本特征表"文件</li>
            <li>从下拉列表选择要处理的探槽</li>
            <li>在参数设置区调整比例尺、样品厚度、位置等参数</li>
            <li>在右侧预览区查看剖面图效果</li>
            <li>点击【导出DXF】按钮输出文件</li>
            </ol>

            <h3>参数说明</h3>
            <ul>
            <li><b>输出比例尺</b>：生成的DXF图件的比例尺，默认1000表示1:1000</li>
            <li><b>样品厚度</b>：样品区域在图面上的宽度（毫米）</li>
            <li><b>样品位置</b>：样品显示在探槽的左侧还是右侧</li>
            <li><b>起点坐标</b>：自动从探槽特征表的0号基点提取，并按输出比例尺换算</li>
            </ul>

            <h3>坐标换算说明</h3>
            <p>输入Excel中的坐标是1:1000比例尺下的坐标。当输出比例尺改变时，起点坐标会自动换算：</p>
            <p>换算公式：输出坐标 = 输入坐标 × (输出比例尺 / 输入比例尺)</p>

            <h3>鼠标操作</h3>
            <ul>
            <li><b>拖拽</b>：平移视图</li>
            <li><b>滚轮</b>：缩放视图</li>
            <li><b>右键</b>：重置视图</li>
            </ul>

            <h3>输入Excel格式</h3>
            <p>Excel文件应包含两个工作表：</p>
            <ul>
            <li><b>采样表</b>：工程编号、起点号、终点号、距离、样号、样长</li>
            <li><b>探槽基本特征表</b>：工程编号、导线基点号、x、y、h、导线长度、方位、坡度</li>
            </ul>
        """)

        layout.addWidget(text)
        dialog.exec_()

    def show_about(self):
        """关于"""
        QMessageBox.about(self, "关于",
            "<h2>探槽样品区DXF生成工具</h2>"
            "<p>版本: 3.0</p>"
            "<p>作者: 消化</p>"
            "<hr>"
            "<p>地质找矿 | 地质灾害防治 | 生态修复</p>"
            "<p>地球化学 | 地球物理 | 遥感地质 | GIS</p>"
        )


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
