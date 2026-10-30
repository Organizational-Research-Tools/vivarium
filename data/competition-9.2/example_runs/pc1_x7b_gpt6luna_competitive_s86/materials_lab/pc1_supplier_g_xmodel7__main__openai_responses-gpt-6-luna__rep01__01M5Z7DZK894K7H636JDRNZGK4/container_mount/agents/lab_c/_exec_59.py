import pandas as pd
r=pd.read_csv('records.csv');
for pr in ['QP-9259','QP-9980','QP-8807','QP-7092','QP-9273','QP-6879']:
 x=r[(r.project==pr)&(r.kind=='qualification')]
 p=x.groupby(['prototype_id','test']).value.agg(['count','mean']).query('count==6').reset_index().pivot(index='prototype_id',columns='test',values='mean')
 print('\n',pr); print(p.to_string())