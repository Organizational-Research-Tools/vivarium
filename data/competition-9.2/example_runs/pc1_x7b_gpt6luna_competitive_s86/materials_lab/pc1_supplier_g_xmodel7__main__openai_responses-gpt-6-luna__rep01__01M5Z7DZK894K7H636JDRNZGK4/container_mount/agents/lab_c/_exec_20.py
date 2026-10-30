import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
for p in ['p_4AQTFYGQBA','p_8E0645AKSJ','p_9BPKMPQZK5']:
 d=x[x.prototype_id==p]
 print('\n',p, d.shape)
 if len(d):
  cols=[c for c in d.columns if c.startswith('module_') or c in ['project_id','prototype_id','record_id','property','value','owner','kind']]
  print(d[cols].head().to_string(index=False))