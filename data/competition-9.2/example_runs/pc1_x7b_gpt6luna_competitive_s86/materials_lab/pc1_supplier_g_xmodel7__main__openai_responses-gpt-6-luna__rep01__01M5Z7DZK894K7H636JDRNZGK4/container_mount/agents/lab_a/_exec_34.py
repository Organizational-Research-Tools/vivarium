import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.project.isin(['QP-6879','QP-3617','QP-9273'])]; p=q.pivot_table(index=['project','prototype_id'],columns=['instrument','kind'],values='value',aggfunc='mean'); print('projects counts',q.groupby('project').prototype_id.nunique());
for proj in q.project.unique():
 z=q[q.project==proj]; print('\n',proj)
 for pid,g in z.groupby('prototype_id'):
  pans={}
  for test,gg in g[g.kind=='qualification'].groupby('instrument'): pans[test]=gg.value.mean()
  if len(pans)>=2: print(pid,pans)
