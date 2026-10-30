import pandas as pd
df = pd.read_csv('records.csv')

# Find record IDs for p_8E3MPG688W (strength) and p_S3WNF6QVR0 (water) and p_8E3MPG688H (heat)
e8 = df[df['prototype_id'].isin(['p_8E3MPG688H','p_8E3MPG688W','p_S3WNF6QVR0'])]
print(e8[['record_id','prototype_id','project','test','kind','value','measured_by']].to_string())

# Also VZ3 family records
print("\n--- VZ3 family ---")
vz = df[df['prototype_id'].isin(['p_VZ3XBYF5AW','p_VZ3XBYF5B5','p_VZ3XBYF5BE'])]
print(vz[['record_id','prototype_id','project','test','kind','value','measured_by']].to_string())
