import pandas as pd
x=pd.read_csv('records.csv'); q=x[(x.project=='QP-6879') & (x.prototype_id.isin(['p_W3B2SY0Z6A','p_HDGZMBDKP9','p_SNNF91F2XB','p_SNNF91F2XD','p_1XF9VFBVYF','p_FZR98ZZADR']))]
print(q.groupby(['prototype_id','instrument','kind','measured_by','requester']).agg(n=('value','size'),mean=('value','mean')).to_string())
print(q[['record_id','prototype_id','kind','instrument','measured_by','requester','value']].to_string(index=False))