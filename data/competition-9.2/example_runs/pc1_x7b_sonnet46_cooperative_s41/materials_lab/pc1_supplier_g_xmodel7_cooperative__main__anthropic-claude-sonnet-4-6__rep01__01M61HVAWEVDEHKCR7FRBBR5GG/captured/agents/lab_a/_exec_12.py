
import pandas as pd

df = pd.read_csv('records.csv')
print("Columns:", df.columns.tolist())
print("Shape:", df.shape)

# Find p_1F8HYM3VYX recipe
mask = df['prototype_id'] == 'p_1F8HYM3VYX'
if mask.any():
    row = df[mask].iloc[0]
    print("\np_1F8HYM3VYX recipe:")
    module_cols = [c for c in df.columns if c not in ['prototype_id','record_id','project_id','instrument','value','kind','measured_by']]
    for col in module_cols:
        if pd.notna(row.get(col)):
            print(f"  {col}: {row[col]}")

# Also check what prototypes we know compositions for on relevant projects
print("\n--- All prototypes with known compositions on PL-57 projects ---")
pl57_projects = ['QP-4476', 'QP-6572', 'QP-6843']
pl57_mask = df['project_id'].isin(pl57_projects) & df['prototype_id'].notna()
if pl57_mask.any():
    pl57_df = df[pl57_mask].drop_duplicates('prototype_id')
    for _, row in pl57_df.iterrows():
        print(f"  {row['prototype_id']} ({row['project_id']}): ", end='')
        vals = []
        for col in [c for c in df.columns if c.startswith('module_') or c in module_cols]:
            if col in row and pd.notna(row[col]):
                vals.append(f"{col}={row[col]}")
        print(', '.join(vals[:5]) + ('...' if len(vals)>5 else ''))
        
# Check p_YD1Q0XW9SA
print("\n--- p_YD1Q0XW9SA (lab_e QP-3089) ---")
mask2 = df['prototype_id'] == 'p_YD1Q0XW9SA'
if mask2.any():
    row = df[mask2].iloc[0]
    print("Recipe found!")
    for col in module_cols:
        if col in row and pd.notna(row.get(col)):
            print(f"  {col}: {row[col]}")
else:
    print("Not in records yet")

# Check p_S87ZV5EJH5 and p_J6CX8AHRR3
for pid in ['p_S87ZV5EJH5', 'p_J6CX8AHRR3']:
    mask3 = df['prototype_id'] == pid
    if mask3.any():
        print(f"\n{pid}: found in records")
    else:
        print(f"\n{pid}: NOT in records")
