import pandas as pd
r=pd.read_csv('records.csv')
print(r.columns.tolist())
print(r.shape)
print(r[r.project.isin(['QP-6879','QP-3617','QP-9273'])].groupby(['project','prototype','instrument','kind']).value.agg(['mean','count']).to_string())