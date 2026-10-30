import pandas as pd
x=pd.read_csv('records.csv')
for project in ['QP-9273','QP-7092','QP-5174','QP-9259','QP-9980']:
 d=x[x.project==project].groupby(['prototype_id','test']).value.mean().unstack()
 print('\n',project,'\n',d.to_string())