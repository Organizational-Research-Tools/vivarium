import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.kind=='qualification']
g=q.groupby(['project','prototype_id','test']).agg(n=('value','count'),mean=('value','mean'),owner=('measured_by','first')).reset_index(); g=g[g.n==6]
# list prototypes complete with >=threshold on each
th={'seal hold temperature':78.625,'edge crush resistance':7.235,'wet strength retained':79.8}
for (proj,pid),z in g.groupby(['project','prototype_id']):
 if set(z.test)==set(th):
  ms=dict(zip(z.test,z['mean']))
  if all(ms[t]>=v for t,v in th.items()): print(proj,pid,ms,dict(zip(z.test,z.owner)))
# complete candidates that only miss one test, sorted by min margin
print('\nnear complete:')
for (proj,pid),z in g.groupby(['project','prototype_id']):
 if set(z.test)==set(th):
  ms=dict(zip(z.test,z['mean'])); margins={t:(ms[t]-th[t])/(0.25 if t=='seal hold temperature' else .03 if t=='edge crush resistance' else .4) for t in th}
  if min(margins.values()) > -3:
   print(proj,pid, {t:round(ms[t],5) for t in th},'margins', {t:round(margins[t],1) for t in th})
