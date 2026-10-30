import pandas as pd
x=pd.read_csv('records.csv')
for pr in ['QP-6879']:
 d=x[x.project==pr]
 for pid,g in d.groupby('prototype_id'):
  row=g.iloc[0]
  comp=[row[c] for c in x.columns[10:22]]
  m=g.groupby('test').value.agg(['size','mean']).to_dict('index')
  print(pid,comp,m)
