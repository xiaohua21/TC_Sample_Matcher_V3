# -*- coding: utf-8 -*-
"""
探槽样品区计算核心模块 V3
直接从V2版本复用计算逻辑

作者：消化
"""

import pandas as pd
import math
from typing import List, Dict, Any, Optional, Tuple


def read_sample_table(path: str) -> pd.DataFrame:
    """读取采样表"""
    df = pd.read_excel(path, sheet_name='采样表')
    df.columns = ['工程编号', '起点号', '终点号', '距离', '样号', '样长']
    return df


def read_tc_feature_table(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """读取探槽特征表，返回每个探槽的特征数据"""
    df = pd.read_excel(path, sheet_name='探槽基本特征表')
    df.columns = ['工程编号', '导线基点号', 'x', 'y', 'h', '导线长度', '方位', '坡度']

    features = {}
    current_tc = None

    for _, row in df.iterrows():
        tc_id = str(row['工程编号']).strip() if pd.notna(row['工程编号']) else None
        if tc_id and tc_id != 'nan':
            current_tc = tc_id
            if current_tc not in features:
                features[current_tc] = []
            features[current_tc].append({
                'point': int(row['导线基点号']),
                'x': float(row['x']),
                'y': float(row['y']),
                'h': float(row['h']),
                'length': 0,
                'azimuth': 0,
                'dip': 0
            })
        elif current_tc and pd.notna(row['导线基点号']):
            azimuth = float(row['方位']) if pd.notna(row['方位']) else 0
            dip = float(row['坡度']) if pd.notna(row['坡度']) else 0
            features[current_tc].append({
                'point': int(row['导线基点号']),
                'x': float(row['x']),
                'y': float(row['y']),
                'h': float(row['h']),
                'length': float(row['导线长度']) if pd.notna(row['导线长度']) else 0,
                'azimuth': azimuth,
                'dip': dip
            })
    return features


def get_tc_start_coords(feature_data: Dict[str, List[Dict[str, Any]]], tc_id: str) -> Tuple[float, float]:
    """获取探槽起点坐标（0号基点的XY坐标）

    Args:
        feature_data: 探槽特征数据
        tc_id: 探槽编号

    Returns:
        (start_x, start_y): 起点坐标
    """
    if tc_id not in feature_data:
        return 0.0, 0.0

    features = feature_data[tc_id]
    # 找0号基点
    for f in features:
        if f['point'] == 0:
            return f['x'], f['y']

    # 如果没有0号点，返回第一个点
    if features:
        return features[0]['x'], features[0]['y']

    return 0.0, 0.0


def get_available_tcs(sample_df: pd.DataFrame) -> List[str]:
    """获取所有有采样数据的探槽ID列表"""
    tc_ids = sample_df['工程编号'].unique()
    result = []
    for tc_id in tc_ids:
        tc_id_str = str(tc_id).strip()
        if tc_id_str and tc_id_str != 'nan':
            result.append(tc_id_str)
    return result


def generate_sample_track_projection(tc_id: str, sample_df: pd.DataFrame,
                                    feature_data: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    生成样轨投影表数据
    返回每行数据列表
    表头: 工程编号, 导线号, 方位, 坡度, 样长, 平距, 方位差, ∑X, ∑Y, X, Y, 样号

    参考公式：
    - 平距 = 样长 * COS(RADIANS(方位))
    - 方位差 = 方位 - 360
    - ∑X = 平距 * COS(RADIANS(方位差))
    - ∑Y = 平距 * SIN(RADIANS(方位差))
    - X = 上一行X + 当前行∑X
    - Y = 上一行Y + 当前行∑Y
    """
    if tc_id not in feature_data:
        return []

    features = feature_data[tc_id]
    tc_samples = sample_df[sample_df['工程编号'] == tc_id].copy()

    result = []
    spanning_samples = {}

    for i in range(len(features) - 1):
        start_point = features[i]['point']
        end_point = features[i + 1]['point']
        seg_length = features[i + 1]['length']
        azimuth = features[i + 1]['azimuth']
        dip = features[i + 1]['dip']

        seg_id = f"{start_point}-{end_point}导"

        # 获取该段的采样数据
        seg_samples = tc_samples[
            (tc_samples['起点号'] == start_point) &
            (tc_samples['终点号'] == end_point)
        ].copy()

        # 添加跨越分界点的样品（从上一段延续过来）
        for sample_id, info in list(spanning_samples.items()):
            seg_samples = pd.concat([seg_samples, pd.DataFrame([{
                '起点号': start_point,
                '终点号': end_point,
                '距离': 0,
                '样号': info['sample_id'],
                '样长': info['remaining_length'],
                '_is_spanning': True
            }])], ignore_index=True)
            del spanning_samples[sample_id]

        # 按距离排序
        if len(seg_samples) > 0:
            seg_samples = seg_samples.sort_values('距离').reset_index(drop=True)

        # 确保所有原始样本有明确的 _is_spanning = False（避免NaN导致布尔判断错误）
        if '_is_spanning' not in seg_samples.columns:
            seg_samples['_is_spanning'] = False
        else:
            seg_samples['_is_spanning'] = seg_samples['_is_spanning'].fillna(False)

        # 如果该段没有采样数据，添加一行表示整段非采样
        if len(seg_samples) == 0:
            result.append({
                '工程编号': tc_id,
                '导线号': seg_id,
                '方位': azimuth,
                '坡度': dip,
                '样长': seg_length,
                '平距': None,
                '方位差': None,
                '累计X': None,
                '累计Y': None,
                'X': seg_length,
                'Y': seg_length,
                '样号': '非采样区',
                '_seg_length': seg_length,
                '_is_segment_start': False
            })
            continue

        first_pos = float(seg_samples.iloc[0]['距离'])

        # 添加从0到第一个采样点的间隔（如果第一个采样点不在0位置）
        if first_pos > 0:
            result.append({
                '工程编号': tc_id,
                '导线号': seg_id,
                '方位': azimuth,
                '坡度': dip,
                '样长': first_pos,
                '平距': None,
                '方位差': None,
                '累计X': None,
                '累计Y': None,
                'X': first_pos,
                'Y': first_pos,
                '样号': '非采样区',
                '_pos': first_pos,
                '_is_segment_start': False
            })

        # 添加每个采样点
        for idx in range(len(seg_samples)):
            curr_row = seg_samples.iloc[idx]
            curr_pos = float(curr_row['距离'])
            curr_length = float(curr_row['样长'])
            sample_id = str(curr_row['样号']).strip()
            is_spanning = curr_row.get('_is_spanning', False)

            # 计算样品在该段内的结束位置
            sample_end_in_seg = curr_pos + curr_length

            # 判断样品是否跨越到下一段
            if sample_end_in_seg > seg_length:
                # 跨越分界点：只添加该样品在本段内的部分
                result.append({
                    '工程编号': tc_id,
                    '导线号': seg_id,
                    '方位': azimuth,
                    '坡度': dip,
                    '样长': seg_length - curr_pos,
                    '平距': None,
                    '方位差': None,
                    '累计X': None,
                    '累计Y': None,
                    'X': seg_length,
                    'Y': seg_length,
                    '样号': sample_id,
                    '_pos': seg_length,
                    '_is_segment_start': False
                })
                # 记录跨越的样品剩余长度
                spanning_samples[sample_id] = {
                    'sample_id': sample_id,
                    'remaining_length': sample_end_in_seg - seg_length
                }
            else:
                # 不跨越：正常添加样品
                result.append({
                    '工程编号': tc_id,
                    '导线号': seg_id,
                    '方位': azimuth,
                    '坡度': dip,
                    '样长': curr_length,
                    '平距': None,
                    '方位差': None,
                    '累计X': None,
                    '累计Y': None,
                    'X': curr_pos + curr_length,
                    'Y': curr_pos + curr_length,
                    '样号': sample_id,
                    '_pos': curr_pos + curr_length,
                    '_is_segment_start': False
                })

                # 添加与下一个采样点之间的间隔
                if idx < len(seg_samples) - 1:
                    next_row = seg_samples.iloc[idx + 1]
                    next_pos = float(next_row['距离'])
                    gap = next_pos - (curr_pos + curr_length)
                    if round(gap, 2) > 0:
                        result.append({
                            '工程编号': tc_id,
                            '导线号': seg_id,
                            '方位': azimuth,
                            '坡度': dip,
                            '样长': gap,
                            '平距': None,
                            '方位差': None,
                            '累计X': None,
                            '累计Y': None,
                            'X': curr_pos + curr_length + gap,
                            'Y': curr_pos + curr_length + gap,
                            '样号': '非采样区',
                            '_pos': curr_pos + curr_length + gap,
                            '_is_segment_start': False
                        })

        # 添加段末间隔（从最后一个采样点到段末端）
        # 只有最后一个样品不是跨越样品时才添加end gap
        last_sample = seg_samples.iloc[-1]
        last_is_spanning = last_sample.get('_is_spanning', False)
        if not last_is_spanning:
            last_pos = float(last_sample['距离'])
            last_length = float(last_sample['样长'])
            end_gap = seg_length - (last_pos + last_length)
            if round(end_gap, 2) > 0:
                result.append({
                    '工程编号': tc_id,
                    '导线号': seg_id,
                    '方位': azimuth,
                    '坡度': dip,
                    '样长': end_gap,
                    '平距': None,
                    '方位差': None,
                    '累计X': None,
                    '累计Y': None,
                    'X': seg_length,
                    'Y': seg_length,
                    '样号': '非采样区',
                    '_pos': seg_length,
                    '_is_segment_start': False
                })

    # 第二遍：计算平距、方位差、∑X、∑Y、X、Y
    cum_x = 0.0
    cum_y = 0.0
    for row in result:
        azimuth = row['方位']
        dip = row['坡度']
        sample_length = row['样长']

        # 计算平距
        pingju = sample_length * math.cos(math.radians(abs(dip)))

        # 计算方位差
        azimuth_diff = azimuth - 360

        # 计算∑X和∑Y
        az_diff_rad = math.radians(azimuth_diff)
        sum_x = pingju * math.cos(az_diff_rad)
        sum_y = pingju * math.sin(az_diff_rad)

        # 计算X和Y（累计坐标）
        curr_x = cum_x + sum_x
        curr_y = cum_y + sum_y

        row['平距'] = pingju
        row['方位差'] = azimuth_diff
        row['累计X'] = sum_x
        row['累计Y'] = sum_y
        row['X'] = curr_x
        row['Y'] = curr_y

        cum_x = curr_x
        cum_y = curr_y

    # 移除临时字段
    for row in result:
        if '_pos' in row:
            del row['_pos']
        if '_seg_length' in row:
            del row['_seg_length']
        if '_is_segment_start' in row:
            del row['_is_segment_start']

    return result


def create_projection_excel_v2(all_results, output_path):
    """
    创建样轨投影表Excel文件 V2.0
    每个探槽一个sheet
    表头: 工程编号, 导线号, 方位, 坡度, 距离, 平距, 导线长度, 段X, 段Y, X, Y, 样号
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        raise ImportError("需要安装 openpyxl 库: pip install openpyxl")

    wb = Workbook()
    # 删除默认sheet
    if 'Sheet' in wb.sheetnames:
        del wb['Sheet']

    for tc_id, data in all_results.items():
        ws = wb.create_sheet(title=str(tc_id)[:31])  # Excel sheet名称最长31字符

        # 写入表头
        headers = ['工程编号', '导线号', '方位', '坡度', '样长', '平距', '方位差', '∑X', '∑Y', 'X', 'Y', '样号']
        for col, header in enumerate(headers, 1):
            ws.cell(1, col, header)

        # 写入起算点行 (X=0, Y=0)
        ws.cell(2, 10, 0)  # X = 0
        ws.cell(2, 11, 0)  # Y = 0

        # 写入数据
        for row_idx, row_data in enumerate(data, 3):  # 从第3行开始（行2是起算点）
            ws.cell(row_idx, 1, row_data['工程编号'])
            ws.cell(row_idx, 2, row_data['导线号'])
            ws.cell(row_idx, 3, row_data['方位'])
            ws.cell(row_idx, 4, row_data['坡度'])
            ws.cell(row_idx, 5, row_data['样长'])
            ws.cell(row_idx, 6, row_data['平距'])
            ws.cell(row_idx, 7, row_data['方位差'])
            ws.cell(row_idx, 8, row_data.get('累计X', 0))
            ws.cell(row_idx, 9, row_data.get('累计Y', 0))
            ws.cell(row_idx, 10, row_data['X'])
            ws.cell(row_idx, 11, row_data['Y'])
            ws.cell(row_idx, 12, row_data['样号'])

    wb.save(output_path)
    return output_path


def generate_all_projection_tables(input_path, output_path, selected_tcs=None):
    """
    主函数：读取输入文件，生成所有探槽的样轨投影表

    Args:
        input_path: 输入Excel文件路径
        output_path: 输出Excel文件路径
        selected_tcs: 可选，要生成的探槽ID列表（None表示全部）
    """
    # 读取数据
    sample_df = read_sample_table(input_path)
    feature_data = read_tc_feature_table(input_path)

    # 获取所有探槽ID
    tc_ids = sample_df['工程编号'].unique()

    # 生成每个探槽的投影数据
    all_results = {}
    for tc_id in tc_ids:
        tc_id_str = str(tc_id).strip()
        if tc_id_str and tc_id_str != 'nan':
            # 如果指定了selected_tcs，则只处理选中的探槽
            if selected_tcs is not None and tc_id_str not in selected_tcs:
                continue
            projection_data = generate_sample_track_projection(tc_id_str, sample_df, feature_data)
            if projection_data:
                all_results[tc_id_str] = projection_data

    # 创建Excel文件
    if all_results:
        create_projection_excel_v2(all_results, output_path)

    return all_results
