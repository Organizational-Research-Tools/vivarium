import pandas as pd
x=pd.read_csv('records.csv');
for p in ['QP-3617','QP-8807','QP-9980','QP-7092','QP-5174']:
 print('\n',p)
 z=x[x.project==p].groupby(['prototype_id','kind','test','measured_by']).size().unstack(fill_value=0)
 print(z.to_string())
