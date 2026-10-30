import pandas as pd
x=pd.read_csv('records.csv')
for proj in ['QP-9980','QP-9219','QP-6879','QP-8807']:
 d=x[(x.project==proj)&(x.kind=='qualification')].groupby(['prototype_id','test']).value.mean().unstack()
 if len(d):
  print('\n',proj, d.to_string())
