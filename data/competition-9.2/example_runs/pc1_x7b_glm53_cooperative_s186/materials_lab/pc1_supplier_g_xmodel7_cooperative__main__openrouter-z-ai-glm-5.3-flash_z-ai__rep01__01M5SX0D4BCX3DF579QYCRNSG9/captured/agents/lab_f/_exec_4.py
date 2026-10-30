import pandas as pd
d=pd.read_csv('records.csv')
w=d[(d.project=='QP-8476')&(d['test']=='water')&(d.requester=='lab_f')&(d.measured_by=='lab_f')]
c=w.groupby('prototype_id')['value'].mean().sort_values(ascending=False)
print(c.head(30))