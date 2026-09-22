# -*- coding: utf-8 -*-
"""显示特定探槽的详细信息"""

import sys
sys.path.insert(0, r"E:\VScodes\TC_Sample_Matcher_V2\src")

from core import read_sample_table, read_tc_feature_table, generate_sample_track_projection

input_file = r"E:\VScodes\TC_Sample_Matcher_V3\data\采样表及探槽基本特征表.xlsx"

sample_df = read_sample_table(input_file)
feature_data = read_tc_feature_table(input_file)

# 显示TC701-1的详细信息
tc_id = 'TC701-1'
result = generate_sample_track_projection(tc_id, sample_df, feature_data)

print(f"探槽 {tc_id} 的详细投影数据:")
print("-" * 80)
print(f"{'序号':<4} {'导线号':<12} {'样号':<10} {'样长':<8} {'X':<12} {'Y':<12}")
print("-" * 80)

for i, row in enumerate(result):
    print(f"{i:<4} {row.get('导线号', ''):<12} {row.get('样号', ''):<10} {row.get('样长', 0):<8.2f} {row.get('X', 0):<12.2f} {row.get('Y', 0):<12.2f}")

# 找出跨导样品
print("\nH样品列表:")
for i, row in enumerate(result):
    sample_id = str(row.get('样号', ''))
    if sample_id.startswith('H'):
        print(f"  {sample_id}: 样长={row.get('样长', 0):.2f}, X={row.get('X', 0):.2f}, 导线={row.get('导线号', '')}")

# 显示所有探槽的样品数量
print("\n\n所有探槽的H样品数量:")
print("-" * 40)
for tc_id in feature_data.keys():
    result = generate_sample_track_projection(tc_id, sample_df, feature_data)
    h_count = sum(1 for r in result if str(r.get('样号', '')).startswith('H'))
    print(f"  {tc_id}: {h_count}个H样品")
