import pandas as pd
x=pd.read_csv('records.csv');
for p in ['QP-9259','QP-9980','QP-6879','QP-3617','QP-9219','QP-5174']:
 d=x[x.project==p]; print('\n',p)
 print(d.groupby(['prototype_id','instrument']).value.agg(['count','mean']).unstack(fill_value='').to_string())