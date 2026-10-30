import pandas as pd
x=pd.read_csv('records.csv')
print(x.shape, x.project.unique())
# aggregate qualification by prototype/project/instrument, recipe signature where composition known
q=x[x.kind=='qualification'].groupby(['project','prototype_id','instrument','measured_by']).agg(mean=('value','mean'),n=('value','count')).reset_index()
for proj in ['QP-6879','QP-3617','QP-8807','QP-9219']:
 print('\n',proj)
 d=q[q.project==proj].pivot_table(index='prototype_id',columns='instrument',values='mean')
 print(d.to_string())
