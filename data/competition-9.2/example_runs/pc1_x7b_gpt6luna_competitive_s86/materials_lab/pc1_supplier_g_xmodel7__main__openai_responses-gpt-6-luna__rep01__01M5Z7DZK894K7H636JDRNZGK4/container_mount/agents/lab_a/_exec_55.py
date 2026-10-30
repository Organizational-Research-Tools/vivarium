import pandas as pd
x=pd.read_csv('records.csv'); p=x[x.kind=='qualification'].groupby(['project','prototype_id','test']).agg(n=('value','count'),m=('value','mean'),owner=('measured_by','first')).reset_index();
for project in ['QP-6879','QP-3617','QP-9273','QP-5174','QP-9980']:
 s=p[p.project==project]; print('\n',project); print(s.to_string(index=False))