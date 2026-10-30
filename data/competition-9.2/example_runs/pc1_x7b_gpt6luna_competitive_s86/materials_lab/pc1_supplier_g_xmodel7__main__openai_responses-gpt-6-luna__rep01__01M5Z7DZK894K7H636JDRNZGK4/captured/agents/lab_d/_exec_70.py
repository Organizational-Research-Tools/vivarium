import pandas as pd
x=pd.read_csv('records.csv'); print(x.columns.tolist()); d=x[x.project.isin(['QP-6879','QP-3617','QP-9273'])].copy(); mods=list(x.columns[11:23]);
for m in mods:d[m]=d[m].fillna('')
for rec,g in d.groupby(mods):
 vals={}
 for i in ['heat','strength','water']:
  q=g[(g.instrument==i)&(g.kind=='qualification')]; e=g[(g.instrument==i)&(g.kind=='exploratory')]
  vals[i]=q.value.mean() if len(q)>=6 else e.value.mean() if len(e) else None
  vals[i+'_qn']=len(q); vals[i+'_en']=len(e)
 if vals['strength'] is not None and vals['water'] is not None and vals['strength']>=7.235 and vals['water']>=79.8:
  print(g.project.iloc[0],g.prototype_id.iloc[0],vals,tuple(rec))