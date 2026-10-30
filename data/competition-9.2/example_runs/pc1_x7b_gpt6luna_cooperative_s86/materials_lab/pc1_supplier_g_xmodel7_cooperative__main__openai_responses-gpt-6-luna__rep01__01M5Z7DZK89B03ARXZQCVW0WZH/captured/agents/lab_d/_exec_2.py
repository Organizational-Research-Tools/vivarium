import pandas as pd
D=pd.read_csv('records.csv')
mods=D.columns[11:].tolist()
print('records per project/instrument')
print(D.groupby(['project','test']).prototype_id.nunique().unstack())
for p,g in D.groupby('project'):
 print('\n',p)
 x=g.groupby('prototype_id').agg(n=('record_id','count'),test=('test',lambda s:','.join(sorted(set(s)))),means=('value','mean')).reset_index()
 for _,r in x.iterrows():
  z=g[g.prototype_id==r.prototype_id]
  vals={t:round(v,4) for t,v in z.groupby('test').value.mean().items()}
  rec=z.iloc[0]; recipe=' '.join(str(rec[m]) for m in mods)
  print(r.prototype_id, r.n, vals, 'H8Z' if rec.base_sheet=='H8Z' else '', recipe)
