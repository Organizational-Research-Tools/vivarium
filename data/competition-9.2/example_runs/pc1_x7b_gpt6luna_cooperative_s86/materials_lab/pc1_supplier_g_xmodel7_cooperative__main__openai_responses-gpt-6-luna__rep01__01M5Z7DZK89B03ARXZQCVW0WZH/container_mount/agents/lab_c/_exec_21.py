import pandas as pd
r=pd.read_csv('records.csv')
print(r.shape)
print(r.columns.tolist())
print(r[r.project_id=='QP-9273'].tail(30).to_string(index=False))