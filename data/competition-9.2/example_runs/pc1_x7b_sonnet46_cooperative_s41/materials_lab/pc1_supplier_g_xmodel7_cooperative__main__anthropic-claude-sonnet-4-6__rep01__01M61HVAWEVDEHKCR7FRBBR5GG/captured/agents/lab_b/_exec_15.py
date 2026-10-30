
import pandas as pd
df = pd.read_csv('records.csv')

recipe_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
               'additive_package_2','additive_package_3','process_profile_1',
               'process_profile_2','process_profile_3','surface_treatment',
               'joint_system','conditioning_step']

T_heat = 78.625; T_str = 7.235; T_wat = 79.8
step_h = 0.25; step_s = 0.03; step_w = 0.4

# Rev C margin
def margin_rc(h, s, w):
    if pd.isna(h) or pd.isna(s) or pd.isna(w): return None
    mh = (h - 77.5) / step_h
    ms = (s - 7.1) / step_s
    mw = (w - 78.0) / step_w
    return min(mh, ms, mw)

# Get qualification panels
qual = df[df['kind']=='qualification']
panel_means = qual.groupby(['project','prototype_id','test'])['value'].mean().reset_index()
panel_means.columns = ['project','prototype_id','test','mean']
piv = panel_means.pivot_table(index=['project','prototype_id'], columns='test', values='mean').reset_index()
piv.columns.name = None

# Rename columns
piv = piv.rename(columns={
    'seal hold temperature': 'heat',
    'edge crush resistance': 'strength',
    'wet strength retained': 'water'
})

# Get recipe for each prototype
recipe_df = df[['prototype_id'] + recipe_cols].dropna(subset=['base_sheet']).drop_duplicates('prototype_id')
piv = piv.merge(recipe_df, on='prototype_id', how='left')

print("=== ALL QUALIFICATION PANELS vs REV C THRESHOLDS ===")
print(f"Thresholds: heat≥{T_heat}, strength≥{T_str}, water≥{T_wat}\n")

for _, row in piv.sort_values(['project','prototype_id']).iterrows():
    h = row.get('heat'); s = row.get('strength'); w = row.get('water')
    hok = f"{h:.3f}{'✓' if pd.notna(h) and h>=T_heat else '✗'}" if pd.notna(h) else '---'
    sok = f"{s:.4f}{'✓' if pd.notna(s) and s>=T_str else '✗'}" if pd.notna(s) else '---'
    wok = f"{w:.2f}{'✓' if pd.notna(w) and w>=T_wat else '✗'}" if pd.notna(w) else '---'
    wm = margin_rc(h, s, w)
    wms = f" wm={wm:.2f}steps" if wm else ""
    gg7 = " **GG7**" if row.get('secondary_sheet')=='GG7' else ""
    print(f"  {row['project']:8s} {row['prototype_id'][:14]} H={hok} S={sok} W={wok}{wms}{gg7}")

print("\n=== TOP STRENGTH VALUES (all records) ===")
str_df = df[df['test']=='edge crush resistance'].sort_values('value', ascending=False)
top = str_df.drop_duplicates('prototype_id').head(20)
for _, row in top.iterrows():
    gg7 = " GG7!" if row.get('secondary_sheet')=='GG7' else ""
    recipe = "/".join([str(row.get(c,'?')) for c in recipe_cols]) if pd.notna(row.get('base_sheet')) else "?"
    print(f"  {row['prototype_id'][:14]} {row['project']:8s} {row['value']:.4f} {row['kind']:13s}{gg7}")
    if pd.notna(row.get('base_sheet')): print(f"    {recipe}")

print("\n=== LAB_F QP-4476 PROTOTYPES STATUS ===")
for pid in ['p_QHRB9W33WW','p_QHRB9W33WY','p_QHRB9W33X0']:
    sub = df[df['prototype_id']==pid]
    print(f"  {pid}: {len(sub)} records")
    for _, r in sub.iterrows():
        print(f"    {r['test']:25s} {r['kind']:13s} {r['value']:.4f}")
