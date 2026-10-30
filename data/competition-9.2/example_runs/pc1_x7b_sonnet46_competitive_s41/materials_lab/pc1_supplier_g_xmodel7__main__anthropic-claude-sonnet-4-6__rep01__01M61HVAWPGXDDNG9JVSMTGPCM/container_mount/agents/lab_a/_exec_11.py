
import pandas as pd
df = pd.read_csv('records.csv')
print("Columns:", df.columns.tolist())
print(f"Total records: {len(df)}")
print()
# Find heat records for p_4V8BTTYF7C
mask = df['prototype_id'] == 'p_4V8BTTYF7C'
print(f"Records for p_4V8BTTYF7C: {mask.sum()}")
print(df[mask][['record_id','project_id','instrument','kind','value']].to_string())
print()
# Also check p_KJZ5KNC3WG
mask2 = df['prototype_id'] == 'p_KJZ5KNC3WG'
print(f"Records for p_KJZ5KNC3WG: {mask2.sum()}")
print(df[mask2][['record_id','project_id','instrument','kind','value']].to_string())
