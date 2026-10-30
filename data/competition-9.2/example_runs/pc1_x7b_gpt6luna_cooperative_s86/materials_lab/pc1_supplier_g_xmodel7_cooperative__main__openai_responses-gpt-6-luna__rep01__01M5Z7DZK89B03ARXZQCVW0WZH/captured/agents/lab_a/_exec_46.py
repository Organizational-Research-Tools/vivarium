import pandas as pd
r=pd.read_csv('records.csv')
print(r.columns.tolist())
print(r[r.project_id.eq('QP-3617')].prototype_id.drop_duplicates().tail(50).to_list())