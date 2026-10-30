
import pandas as pd
df = pd.read_csv('records.csv')

# Find heat records for p_4V8BTTYF7C
mask = df['prototype_id'] == 'p_4V8BTTYF7C'
sub = df[mask][['record_id','project','instrument','kind','value','measured_by']]
print(f"Records for p_4V8BTTYF7C ({mask.sum()} total):")
print(sub.to_string())
print()

# Qualification heat records specifically
heat_qual = df[(df['prototype_id']=='p_4V8BTTYF7C') & (df['kind']=='qualification') & (df['instrument']=='heat')]
print(f"Heat qualification records for p_4V8BTTYF7C: {len(heat_qual)}")
print(heat_qual[['record_id','value','measured_by']].to_string())
print()

# p_KJZ5KNC3WG
mask2 = df['prototype_id'] == 'p_KJZ5KNC3WG'
sub2 = df[mask2][['record_id','project','instrument','kind','value','measured_by']]
print(f"Records for p_KJZ5KNC3WG ({mask2.sum()} total):")
print(sub2.to_string())
