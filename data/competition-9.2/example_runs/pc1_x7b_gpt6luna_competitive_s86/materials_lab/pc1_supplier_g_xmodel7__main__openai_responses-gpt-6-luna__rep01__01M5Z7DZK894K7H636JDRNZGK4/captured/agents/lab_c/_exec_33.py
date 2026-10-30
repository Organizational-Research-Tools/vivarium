import pandas as pd
r=pd.read_csv('records.csv')
print(r.columns.tolist())
print(r[r['project_id'].eq('QP-6879')].tail(20).to_string(index=False))