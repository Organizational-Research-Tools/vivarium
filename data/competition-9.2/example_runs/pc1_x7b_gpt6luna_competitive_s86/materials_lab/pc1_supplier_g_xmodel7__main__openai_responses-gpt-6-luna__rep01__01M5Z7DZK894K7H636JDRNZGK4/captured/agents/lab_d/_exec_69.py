import pandas as pd
x=pd.read_csv('records.csv'); d=x[x.project=='QP-3617'].copy(); mods=list(x.columns[11:23]);
for m in mods:d[m]=d[m].fillna('')
for rec,g in d.groupby(mods):
 vals={}
 for i in ['heat','strength','water']:
  q=g[(g.instrument==i)&(g.kind=='qualification')]; e=g[(g.instrument==i)&(g.kind=='exploratory')]
  vals[i]=q.value.mean() if len(q)>=6 else e.value.mean() if len(e) else None
  vals[i+'_n']=len(q) if len(q)>=6 else len(e)
 if vals['strength'] and vals['water'] and vals['strength']>=7.235 and vals['water']>=79.8 and vals['heat'] is None:
  print(g.prototype_id.iloc[0],vals,tuple(rec))
