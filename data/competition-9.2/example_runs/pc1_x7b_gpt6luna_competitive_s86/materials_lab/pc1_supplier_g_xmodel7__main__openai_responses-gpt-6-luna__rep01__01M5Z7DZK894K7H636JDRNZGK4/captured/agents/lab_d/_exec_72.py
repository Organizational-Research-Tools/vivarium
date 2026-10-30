import pandas as pd
x=pd.read_csv('records.csv'); mods=list(x.columns[11:23]);
for m in mods:x[m]=x[m].fillna('')
for key,g in x.groupby(['project']+mods):
 pr=key[0]; rec=key[1:]
 means=[]; full=True
 for i,t in [('heat',78.625),('strength',7.235),('water',79.8)]:
  q=g[(g.instrument==i)&(g.kind=='qualification')]
  if len(q)<6: full=False; means.append(None)
  else: means.append(q.value.mean())
 if pr in ['QP-6879','QP-3617','QP-9273'] and full and all(means[i]>=t for i,t in enumerate([78.625,7.235,79.8])):
  print(pr, rec[0], g.prototype_id.iloc[0],means)