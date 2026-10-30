import pandas as pd
x=pd.read_csv('records.csv')
for p in ['QP-3617','QP-9980','QP-7092','QP-5174','QP-9273']:
 g=x[x.project==p]
 print('\n',p, g.groupby(['prototype_id','test']).value.agg(['count','mean']).to_string())