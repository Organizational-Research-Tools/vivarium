import pandas as pd
df = pd.read_csv('records.csv')
ids = ['p_BKVHDNHTCH','p_9T7PGPYM54','p_9T7PGPYM56','p_25SH4G2DQE','p_V3DS5HS1PT','p_6HRWVWM6EN']
s = df[(df.instrument=='strength')&(df.kind=='exploratory')&(df.prototype_id.isin(ids))]
print(s.groupby('prototype_id')['value'].agg(['mean','count','min','max']))
g = [x for x in df.prototype_id.unique() if 'p_EE8A5DB0' in x or 'p_B0A2' in x]
print(s[s.prototype_id.isin(g)])
# strength exploratory on new grants generally (QP-5993 & QP-3777):
t = df[(df.instrument=='strength')&(df.kind=='exploratory')&(df.project.isin(['QP-5993','QP-3777']))]
print(t.groupby(['prototype_id','project','measured_by'])['value'].agg(['mean','count']).sort_values('mean',ascending=False))
