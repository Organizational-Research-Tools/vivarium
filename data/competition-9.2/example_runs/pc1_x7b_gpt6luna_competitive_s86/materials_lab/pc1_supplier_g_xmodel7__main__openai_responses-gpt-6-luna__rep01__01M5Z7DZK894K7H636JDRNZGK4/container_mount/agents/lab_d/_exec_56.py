import pandas as pd
x=pd.read_csv('records.csv')
z=x[x.project.eq('QP-3617')].groupby(['prototype_id','instrument','kind','test','measured_by']).value.agg(['count','mean']).reset_index()
print(z[z.prototype_id.str.startswith(('p_5ZN','p_W3C','p_H6M'))].to_string(index=False))