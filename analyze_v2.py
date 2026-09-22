# -*- coding: utf-8 -*-
"""
详细分析V2的计算逻辑
"""

import sys
sys.path.insert(0, r"E:\VScodes\TC_Sample_Matcher_V2\src")

from core import read_sample_table, read_tc_feature_table, generate_sample_track_projection

input_file = r"E:\VScodes\TC_Sample_Matcher_V3\data\采样表及探槽基本特征表.xlsx"

sample_df = read_sample_table(input_file)
feature_data = read_tc_feature_table(input_file)

# 选择一个有跨导样品的探槽
tc_id = 'TC701-1'
print(f"=" * 80)
print(f"探槽 {tc_id} 的详细分析")
print(f"=" * 80)

# 显示探槽特征
print(f"\n探槽特征 (导线数据):")
print(f"-" * 80)
for i, f in enumerate(feature_data[tc_id]):
    print(f"  点{i}: point={f['point']}, x={f['x']}, y={f['y']}, length={f['length']}, azimuth={f['azimuth']}, dip={f['dip']}")

# 生成投影数据
result = generate_sample_track_projection(tc_id, sample_df, feature_data)

print(f"\n投影数据 (前20行):")
print(f"-" * 80)
print(f"{'行':<3} {'导线号':<10} {'样号':<8} {'样长':<8} {'方位':<8} {'坡度':<8} {'X':<10} {'Y':<10}")
print(f"-" * 80)

for i, row in enumerate(result[:20]):
    print(f"{i:<3} {row.get('导线号', ''):<10} {row.get('样号', ''):<8} "
          f"{row.get('样长', 0):<8.2f} {row.get('方位', 0):<8.1f} {row.get('坡度', 0):<8.1f} "
          f"{row.get('X', 0):<10.2f} {row.get('Y', 0):<10.2f}")

print(f"\n统计:")
h_samples = [r for r in result if str(r.get('样号', '')).startswith('H')]
non_samples = [r for r in result if str(r.get('样号', '')) == '非采样区']
print(f"  H样品数: {len(h_samples)}")
print(f"  非采样区数: {len(non_samples)}")
print(f"  总记录数: {len(result)}")

print(f"\n各导线的样品分布:")
print(f"-" * 80)
current_segment = None
for i, row in enumerate(result):
    seg = row.get('导线号', '')
    if seg != current_segment:
        current_segment = seg
        print(f"\n{seg}:")
    sample_id = row.get('样号', '')
    if sample_id.startswith('H'):
        print(f"  {sample_id}: 样长={row.get('样长', 0):.2f}, X={row.get('X', 0):.2f}")
