import pandas as pd
r=pd.read_csv('records.csv')
q=r[(r.project=='QP-6879') & (r.test.str.contains('heat', case=False))]
print(q.shape)
print(q.groupby(['prototype_id','kind','measured_by']).value.agg(['mean','min','max','count']).sort_values('mean',ascending=False).head(25).to_string())
print('\nknown compositions top panel means:')
print(q.groupby(['prototype_id','kind']).value.mean().sort_values(ascending=False).head(40).to_string())