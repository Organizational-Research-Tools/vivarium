
# Quick check: mean of p_8F860GY05C strength panel
readings = [7.18598, 7.19615, 7.12922, 7.13492, 7.17314, 7.16669]
mean = sum(readings)/len(readings)
print(f"p_8F860GY05C strength panel mean: {mean:.4f} kN/m (Rev C needs 7.235) → {'PASS' if mean >= 7.235 else 'FAIL'}")
print(f"Gap: {7.235 - mean:.4f} kN/m = {(7.235 - mean)/0.03:.2f} steps")

import pandas as pd
df = pd.read_csv('records.csv')

# Check what prototypes are in QP-7212 and QP-3473 with any qualifying panels
recipe_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
               'additive_package_2','additive_package_3','process_profile_1',
               'process_profile_2','process_profile_3','surface_treatment',
               'joint_system','conditioning_step']

T_heat = 78.625; T_str = 7.235; T_wat = 79.8

qual = df[df['kind']=='qualification']
panel_means = qual.groupby(['project','prototype_id','test'])['value'].mean().reset_index()
piv = panel_means.pivot_table(index=['project','prototype_id'], columns='test', values='mean').reset_index()
piv.columns.name = None
piv = piv.rename(columns={'seal hold temperature':'heat','edge crush resistance':'strength','wet strength retained':'water'})

# PL-95 projects
print("\n=== QP-3473 and QP-7212 qualification data ===")
pl95 = piv[piv['project'].isin(['QP-3473','QP-7212'])]
recipe_df = df[['prototype_id'] + recipe_cols].dropna(subset=['base_sheet']).drop_duplicates('prototype_id')
pl95 = pl95.merge(recipe_df, on='prototype_id', how='left')
for _, row in pl95.iterrows():
    h = row.get('heat'); s = row.get('strength'); w = row.get('water')
    gg7 = " **GG7**" if row.get('secondary_sheet')=='GG7' else ""
    hok = f"{h:.3f}{'✓' if pd.notna(h) and h>=T_heat else '✗'}" if pd.notna(h) else '---'
    sok = f"{s:.4f}{'✓' if pd.notna(s) and s>=T_str else '✗'}" if pd.notna(s) else '---'
    wok = f"{w:.2f}{'✓' if pd.notna(w) and w>=T_wat else '✗'}" if pd.notna(w) else '---'
    print(f"  {row['project']:8s} {row['prototype_id'][:16]} H={hok} S={sok} W={wok}{gg7}")

# Any prototype with heat >= 78.625 in QP-7212 or QP-3473 — look at individual records too
print("\n=== All heat records ≥78.625 in QP-7212 / QP-3473 ===")
heat_rec = df[(df['test']=='seal hold temperature') & (df['project'].isin(['QP-3473','QP-7212']))]
top_heat = heat_rec.groupby('prototype_id').agg({'value':'mean','project':'first','secondary_sheet':'first'}).reset_index()
top_heat = top_heat[top_heat['value'] >= 78.625].sort_values('value', ascending=False)
for _, row in top_heat.iterrows():
    gg7 = " GG7!" if row.get('secondary_sheet')=='GG7' else ""
    print(f"  {row['prototype_id']:16s} {row['project']:8s} heat={row['value']:.3f}°C{gg7}")
