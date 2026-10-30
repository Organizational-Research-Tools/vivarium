import pandas as pd
x=pd.read_csv('records.csv'); x=x[x.base_sheet!='H8Z']
q=x[x.kind=='qualification'].groupby(['project','prototype_id','test']).value.agg(['mean','count']).reset_index()
p=q.pivot(index=['project','prototype_id'],columns='test',values='mean')
print('qual strength & water revC:')
print(p[(p['edge crush resistance']>=7.235)&(p['wet strength retained']>=79.8)].to_string())
print('strength>= threshold, no water or water pass')
print(p[(p['edge crush resistance']>=7.235)&((p['wet strength retained']>=79.8)|p['wet strength retained'].isna())].to_string())
