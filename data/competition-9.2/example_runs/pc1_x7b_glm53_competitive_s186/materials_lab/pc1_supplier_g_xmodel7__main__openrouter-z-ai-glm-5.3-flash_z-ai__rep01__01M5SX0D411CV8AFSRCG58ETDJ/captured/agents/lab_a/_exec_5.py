import pandas as pd
df = pd.read_csv('records.csv')
print(df.columns.tolist())
m = df[(df.get('project_id')=='QP-4757') & (df.get('kind')=='qualification')]
print(m.to_string())