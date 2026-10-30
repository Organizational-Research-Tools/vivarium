import pandas as pd
x=pd.read_csv('records.csv')
# list prototypes QP3617, QP9259, QP6879 all local record summaries
for proj in ['QP-3617','QP-9259','QP-6879','QP-5174','QP-9273']:
 d=x[(x.project==proj)&(x.kind=='qualification')].groupby(['prototype_id','test']).value.agg(['mean','count']).round(4)
 if len(d):
  print('\n',proj)
  print(d.to_string())