
import pandas as pd

df = pd.read_csv('records.csv')
heat_qual = df[(df['kind'] == 'qualification') & (df['instrument'] == 'heat')]

# Get record IDs for the three lab_e requested prototypes
targets = ['p_02A6NY9WNM', 'p_BZB62TCK50', 'p_2058095Z34']
for pid in targets:
    rows = heat_qual[heat_qual['prototype_id'] == pid]
    print(f"\n{pid} ({rows['project'].iloc[0] if len(rows)>0 else 'N/A'}) — mean {rows['value'].mean():.4f}°C")
    print(f"  Records: {', '.join(rows['record_id'].tolist())}")

# Also show all lab_b prototypes in records
print("\n--- Lab_b prototypes in records ---")
lab_b_pids = ['p_KAZ5RD12DD','p_PHXDGYDJZ4','p_VWGXN45KEP','p_5626AZQYBH',
               'p_JJXGRVP079','p_HQ697J921E','p_KJZ5KNC3WG','p_G7FKD5Q8G6','p_6D4GP1RVR9']
for pid in lab_b_pids:
    rows = heat_qual[heat_qual['prototype_id'] == pid]
    if len(rows) > 0:
        print(f"  {pid}: project={rows['project'].iloc[0]}, n={len(rows)}, mean={rows['value'].mean():.2f}")
    else:
        print(f"  {pid}: NOT in heat_qual records")
        
# Check all instruments
print("\n--- All instruments for lab_b prototypes ---")
for pid in lab_b_pids:
    rows = df[df['prototype_id'] == pid]
    if len(rows) > 0:
        print(f"  {pid}: {rows[['project','instrument','kind','measured_by']].drop_duplicates().to_string()}")
