# -*- coding: utf-8 -*-
"""
比较V2和V3的计算结果是否一致
"""

import sys
sys.path.insert(0, r"E:\VScodes\TC_Sample_Matcher_V2\src")
sys.path.insert(0, r"E:\VScodes\TC_Sample_Matcher_V3\src")

from core import read_sample_table, read_tc_feature_table, generate_sample_track_projection

input_file = r"E:\VScodes\TC_Sample_Matcher_V3\data\采样表及探槽基本特征表.xlsx"

sample_df = read_sample_table(input_file)
feature_data = read_tc_feature_table(input_file)

# 显示所有探槽
print("所有探槽列表:")
for i, tc_id in enumerate(feature_data.keys()):
    print(f"  {i+1}. {tc_id}")

# 选择前3个有数据的探槽进行比较
test_trenches = list(feature_data.keys())[:3]

print("\n" + "=" * 100)
print("V2 vs V3 计算结果比较")
print("=" * 100)

for tc_id in test_trenches:
    print(f"\n{'=' * 80}")
    print(f"探槽: {tc_id}")
    print("=" * 80)

    # 显示探槽特征（导线数据）
    print(f"\n探槽特征 (导线数据):")
    print("-" * 80)
    for i, f in enumerate(feature_data[tc_id]):
        print(f"  点{i}: point={f['point']}, x={f['x']:.2f}, y={f['y']:.2f}, "
              f"length={f['length']:.2f}, azimuth={f['azimuth']:.1f}, dip={f['dip']:.1f}")

    # 生成投影数据
    result = generate_sample_track_projection(tc_id, sample_df, feature_data)

    print(f"\n投影数据 (前10行):")
    print("-" * 100)
    header = f"{'序号':<4} {'导线号':<10} {'样号':<8} {'样长':<8} {'方位':<8} {'坡度':<8} {'X':<12} {'Y':<12}"
    print(header)
    print("-" * 100)

    for i, row in enumerate(result[:10]):
        print(f"{i:<4} {row.get('导线号', ''):<10} {row.get('样号', ''):<8} "
              f"{row.get('样长', 0):<8.2f} {row.get('方位', 0):<8.1f} {row.get('坡度', 0):<8.1f} "
              f"{row.get('X', 0):<12.2f} {row.get('Y', 0):<12.2f}")

    # 显示所有H样品的累计X和Y
    print(f"\nH样品累计坐标:")
    print("-" * 80)
    for i, row in enumerate(result):
        sample_id = str(row.get('样号', ''))
        if sample_id.startswith('H'):
            print(f"  {sample_id}: X={row.get('X', 0):.2f}, Y={row.get('Y', 0):.2f}, 样长={row.get('样长', 0):.2f}")

print("\n" + "=" * 100)
print("计算结果验证完成")
print("=" * 100)