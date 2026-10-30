import pandas as pd
df = pd.read_csv('records.csv')
print(df.columns.tolist())
m = df[(df.get('prototype_id')=='p_7ZJ7YBKK9E')]
print(m[['record_id','property','kind','measured_by','value']].to_string() if 'prototype_id' in df.columns else df.head())