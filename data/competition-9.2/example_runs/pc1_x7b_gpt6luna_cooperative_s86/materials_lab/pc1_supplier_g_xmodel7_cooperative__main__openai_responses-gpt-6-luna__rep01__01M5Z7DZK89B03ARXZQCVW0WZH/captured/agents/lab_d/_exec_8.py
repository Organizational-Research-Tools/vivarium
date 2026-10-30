import pandas as pd
r=pd.read_csv('records.csv')
print(r.columns.tolist())
print(r[r['prototype_id'].isin(['p_NQYNDKZ3C8','p_NQYNDKZ3CA','p_NQYNDKZ3CG','p_NQYNDKZ3CJ'])].groupby(['prototype_id','instrument','property'])['value'].agg(['mean','count']).to_string())
print(r[r['prototype_id'].isin(['p_NQYNDKZ3C8','p_NQYNDKZ3CA','p_NQYNDKZ3CG','p_NQYNDKZ3CJ'])].drop_duplicates('prototype_id')[['prototype_id','project_id']+[c for c in r if c.startswith('module_')]].to_string(index=False))