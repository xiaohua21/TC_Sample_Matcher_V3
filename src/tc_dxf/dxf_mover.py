# -*- coding: utf-8 -*-
"""
DXF文件整体移动工具（纯文本替换方式）
作者：消化

功能：
- 读取已导出的DXF文件
- 根据目标坐标计算偏移量
- 用文本替换方式移动所有坐标点
- 保存为新的DXF文件

优点：
- 不依赖ezdxf的实体处理，避免兼容性问题
- 支持所有类型的实体（HATCH、SOLID等）
"""

import os
import re
from typing import Tuple, Optional


class DXFMover:
    """DXF文件整体移动工具（文本替换方式）"""

    def __init__(self):
        self.input_path: str = ""
        self.output_path: str = ""
        self.offset_x: float = 0.0
        self.offset_y: float = 0.0
        self.start_x: float = 0.0
        self.start_y: float = 0.0

    @staticmethod
    def check_ezdxf() -> bool:
        """此版本不需要ezdxf"""
        return True

    def load_dxf(self, file_path: str) -> bool:
        """加载DXF文件并分析起点坐标

        Args:
            file_path: DXF文件路径

        Returns:
            是否加载成功
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        self.input_path = file_path

        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # 尝试找到探槽起点坐标
        # 方法1：查找"起点"文字后面的坐标
        start_pattern = re.compile(r'起点[^\n]*\s+10\s+([-\d.]+)\s+20\s+([-\d.]+)', re.IGNORECASE)
        match = start_pattern.search(content)
        if match:
            self.start_x = float(match.group(1))
            self.start_y = float(match.group(2))
            print(f"[DXF Mover] 从标注找到起点: ({self.start_x}, {self.start_y})")
            return True

        # 方法2：找到第一条LINE的起点作为参考
        line_pattern = re.compile(r'LINE.*?10\s+([-\d.]+)\s+20\s+([-\d.]+)', re.DOTALL)
        match = line_pattern.search(content)
        if match:
            self.start_x = float(match.group(1))
            self.start_y = float(match.group(2))
            print(f"[DXF Mover] 从第一条线找到起点: ({self.start_x}, {self.start_y})")
            return True

        print(f"[DXF Mover] 未找到起点坐标，使用默认值")
        self.start_x = 0.0
        self.start_y = 0.0
        return True

    def calculate_offset(self, target_x: float, target_y: float) -> Tuple[float, float]:
        """计算偏移量

        Args:
            target_x: 目标起点X坐标
            target_y: 目标起点Y坐标

        Returns:
            (offset_x, offset_y): X和Y方向的偏移量
        """
        self.offset_x = target_x - self.start_x
        self.offset_y = target_y - self.start_y

        print(f"[DXF Mover] 起点坐标: ({self.start_x}, {self.start_y})")
        print(f"[DXF Mover] 目标坐标: ({target_x}, {target_y})")
        print(f"[DXF Mover] 偏移量: ({self.offset_x}, {self.offset_y})")

        return self.offset_x, self.offset_y

    def move_all(self, output_path: str, offset_x: float = None, offset_y: float = None) -> str:
        """移动所有坐标点

        Args:
            output_path: 输出文件路径
            offset_x: X方向偏移量
            offset_y: Y方向偏移量

        Returns:
            输出文件路径
        """
        if offset_x is not None:
            self.offset_x = offset_x
        if offset_y is not None:
            self.offset_y = offset_y

        print(f"[DXF Mover] 开始移动，偏移量: ({self.offset_x}, {self.offset_y})")

        # 读取原文件，按行处理
        with open(self.input_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # 处理每一行，找到group code并替换下一行的值
        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i].rstrip('\r\n')
            new_lines.append(lines[i])

            # 获取group code
            group_code = line.strip()

            # 检查是否是X坐标组 (10-19)
            if group_code in ['10', '11', '12', '13', '14', '15', '16', '17', '18', '19']:
                # 下一行是X坐标值
                if i + 1 < len(lines):
                    value_line = lines[i + 1].rstrip('\r\n')
                    try:
                        value = float(value_line)
                        new_value = value + self.offset_x
                        new_lines.append(f"{new_value:.6f}\n")
                        i += 2
                        continue
                    except ValueError:
                        pass

            # 检查是否是Y坐标组 (20-29)
            elif group_code in ['20', '21', '22', '23', '24', '25', '26', '27', '28', '29']:
                # 下一行是Y坐标值
                if i + 1 < len(lines):
                    value_line = lines[i + 1].rstrip('\r\n')
                    try:
                        value = float(value_line)
                        new_value = value + self.offset_y
                        new_lines.append(f"{new_value:.6f}\n")
                        i += 2
                        continue
                    except ValueError:
                        pass

            i += 1

        # 保存文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        self.output_path = output_path
        print(f"[DXF Mover] 已保存到: {output_path}")

        return output_path

    def find_latest_dxf(self, directory: str, trench_id: str = None) -> Optional[str]:
        """在指定目录中查找最新的DXF文件

        Args:
            directory: 要搜索的目录
            trench_id: 可选的探槽ID，用于过滤文件名

        Returns:
            最新DXF文件路径，如果没有找到返回None
        """
        if not os.path.exists(directory):
            return None

        dxf_files = []
        for filename in os.listdir(directory):
            if filename.lower().endswith('.dxf'):
                if trench_id is None or trench_id in filename:
                    file_path = os.path.join(directory, filename)
                    mtime = os.path.getmtime(file_path)
                    dxf_files.append((file_path, mtime))

        if not dxf_files:
            return None

        dxf_files.sort(key=lambda x: x[1], reverse=True)
        latest = dxf_files[0][0]
        print(f"[DXF Mover] 找到最新DXF: {latest}")
        return latest