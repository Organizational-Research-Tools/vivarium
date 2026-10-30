
import pandas as pd
df = pd.read_csv('records.csv')

recipe_cols = ['base_sheet','secondary_sheet','binder_system','additive_package_1',
               'additive_package_2','additive_package_3','process_profile_1',
               'process_profile_2','process_profile_3','surface_treatment',
               'joint_system','conditioning_step']

# Find all strength readings, sorted descending
str_df = df[df['test']=='strength'].copy()
print(f"Total strength records: {len(str_df)}")
print(f"\n=== TOP STRENGTH READINGS (exploratory+panel) ===")
top = str_df.sort_values('value', ascending=False).head(40)
for _, row in top.iterrows():
    recipe = "/".join([str(row.get(c,'?')) for c in recipe_cols]) if pd.notna(row.get('base_sheet')) else "unknown"
    flag = " *** GG7" if row.get('secondary_sheet','') == 'GG7' else ""
    bar = "✓" if row['value'] >= 7.235 else ("~" if row['value'] >= 7.19 else "✗")
    print(f"  {row['prototype_id'][:14]} {row['project']:8s} {row['kind']:11s} {row['value']:.4f}{bar}{flag}")
    if pd.notna(row.get('base_sheet')):
        print(f"    {recipe}")

# Find prototypes granted (that I can measure) that I haven't yet run strength on
print("\n=== PROTOTYPES GRANTED (no strength data yet) ===")
granted = str_df.copy()
all_pids = df['prototype_id'].unique()
measured_pids = str_df['prototype_id'].unique()
print(f"Prototypes with strength data: {len(measured_pids)}")
print(f"All known prototypes: {len(all_pids)}")

# check lab_f's new QP-4476 prototypes
lab_f_pids = ['p_QHRB9W33WW','p_QHRB9W33WY','p_QHRB9W33X0']
print("\n=== LAB_F QP-4476 PROTOTYPES (STRENGTH STATUS) ===")
for pid in lab_f_pids:
    sub = df[df['prototype_id']==pid]
    str_sub = sub[sub['test']=='strength']
    print(f"  {pid}: {len(sub)} total records, strength readings: {len(str_sub)}")
    if len(str_sub) > 0:
        print(f"    strength values: {str_sub['value'].tolist()}")
