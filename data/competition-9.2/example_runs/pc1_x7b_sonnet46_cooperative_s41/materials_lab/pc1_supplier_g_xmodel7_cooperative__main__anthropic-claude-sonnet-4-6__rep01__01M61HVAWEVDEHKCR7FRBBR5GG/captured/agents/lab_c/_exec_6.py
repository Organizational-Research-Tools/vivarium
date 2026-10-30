
import pandas as pd

df = pd.read_csv('records.csv')
comp_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
             'additive_package_2','additive_package_3','process_profile_1',
             'process_profile_2','process_profile_3','surface_treatment',
             'joint_system','conditioning_step']

# Show complete recipe + all-test summary for each known recipe group
panels = df[df['kind']=='qualification'].groupby(['project','prototype_id','test'])['value'].mean().reset_index()
pivot = panels.pivot_table(index=['project','prototype_id'], columns='test', values='mean')
pivot.columns = ['strength','heat','water']
pivot = pivot.reset_index()
comp = df[comp_cols + ['prototype_id']].drop_duplicates('prototype_id')
full = pivot.merge(comp, on='prototype_id', how='left')

# Print summary of all projects with partial or complete data
print("=== COMPLETE RECIPE SUMMARY ===")
for proj in sorted(full['project'].unique()):
    proj_data = full[full['project']==proj]
    # Group by recipe - same composition will appear as multiple prototype_ids
    # Use comp to group
    print(f"\n{proj}:")
    for _, row in proj_data.iterrows():
        h = f"{row['heat']:.2f}°C {'✓' if pd.notna(row['heat']) and row['heat']>=77.5 else '✗' if pd.notna(row['heat']) else '?'}"
        s = f"{row['strength']:.3f} kN/m {'✓' if pd.notna(row['strength']) and row['strength']>=7.1 else '✗' if pd.notna(row['strength']) else '?'}"
        w = f"{row['water']:.2f}% {'✓' if pd.notna(row['water']) and row['water']>=78.0 else '✗' if pd.notna(row['water']) else '?'}"
        gg7 = " [GG7!]" if row.get('secondary_sheet')=='GG7' else ""
        print(f"  {row['prototype_id']}: H={h} S={s} W={w}{gg7}")
        print(f"    Recipe: {row['base_sheet']}|{row['secondary_sheet']}|{row['binder_system']}|{row['additive_package_1']}|{row['additive_package_2']}|{row['additive_package_3']}|{row['process_profile_1']}|{row['process_profile_2']}|{row['process_profile_3']}|{row['surface_treatment']}|{row['joint_system']}|{row['conditioning_step']}")

print("\n\n=== PROPOSED NEW RECIPES (FIXING WATER VIA JOINT=9FU, AP3=L6C) ===")
# For each project that fails water, show what change we'd make

# QP-3089 non-GG7: DA9|3HW|T9M|57T|6FA|QJ4|4QB|C5Q|X9F|ZW3|57U|G8Q  heat✓ str✓ water✗
# Fix: QJ4→L6C, 57U→9FU
print("QP-3089 new: DA9|3HW|T9M|57T|6FA|L6C|4QB|C5Q|X9F|ZW3|9FU|G8Q")

# QP-7212: P2G|YX8|NN7|5FE|S2J|4PE|4QB|VA8|N7N|ZW3|57U|G8Q  heat✓ str✓ water✗
# Fix: 4PE→L6C, 57U→9FU
print("QP-7212 new: P2G|YX8|NN7|5FE|S2J|L6C|4QB|VA8|N7N|ZW3|9FU|G8Q")

# QP-4476: JA8|3HW|T9M|QJ2|6FA|QJ4|62D|VA8|N4L|7KL|57U|6JZ  heat✓ str✓ water✗
# Fix: QJ4→L6C, 57U→9FU
print("QP-4476 new: JA8|3HW|T9M|QJ2|6FA|L6C|62D|VA8|N4L|7KL|9FU|6JZ")

print("\nInteraction check (additive_package_2 × joint_system × additive_package_3):")
print("QP-3089: 6FA × 9FU × L6C  → matches QP-6843 pattern (78.96% water)")
print("QP-7212: S2J × 9FU × L6C  → matches QP-6843 pattern (79.00% water)")
print("QP-4476: 6FA × 9FU × L6C  → same as QP-3089")
