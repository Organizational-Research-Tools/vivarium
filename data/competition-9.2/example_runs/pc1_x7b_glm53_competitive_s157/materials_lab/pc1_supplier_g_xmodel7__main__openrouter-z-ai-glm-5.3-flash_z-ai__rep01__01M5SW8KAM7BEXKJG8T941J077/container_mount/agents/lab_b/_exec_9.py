import pandas as pd
df = pd.read_csv('records.csv')
# all qualification panels I can cite anywhere
q = df[df.kind=='qualification']
t = q.pivot_table(index=['project','prototype_id','measured_by'], columns='test', values='value', aggfunc=['mean','count'])
print(t.to_string())