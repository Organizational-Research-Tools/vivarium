import pandas as pd
x=pd.read_csv('records.csv')
# unique recipes for open projects, qualification panels mean by prototype and instrument
for p in ['QP-5174','QP-7092','QP-9273']:
 d=x[x.project==p]
 print('\n',p)
 print(d.groupby(['prototype_id','instrument','test']).value.agg(['count','mean']).to_string())
 print('prototypes',d.prototype_id.nunique())
