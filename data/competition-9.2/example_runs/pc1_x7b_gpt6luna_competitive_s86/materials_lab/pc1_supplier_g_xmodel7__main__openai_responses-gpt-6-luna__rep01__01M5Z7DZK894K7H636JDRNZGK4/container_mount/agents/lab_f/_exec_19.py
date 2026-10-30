import pandas as pd
r=pd.read_csv('records.csv')
r=r[r.project.isin(['QP-6879','QP-3617','QP-9273'])]
g=r.groupby(['project','prototype_id','test','kind']).value.agg(['mean','count']).reset_index()
print(g.to_string(index=False))