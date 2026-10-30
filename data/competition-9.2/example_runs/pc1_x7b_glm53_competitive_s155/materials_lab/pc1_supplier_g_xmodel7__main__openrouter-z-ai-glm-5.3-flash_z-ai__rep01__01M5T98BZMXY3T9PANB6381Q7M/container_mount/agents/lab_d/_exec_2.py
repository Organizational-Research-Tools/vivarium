import pandas as pd
df = pd.read_csv('records.csv')
df = df[df.prototype_id.isin(['p_F266GFQYD5','p_V5WECMBJZK'])] if 'prototype_id' in df.columns else df
print(df.columns.tolist())
print(df.tail(40).to_string())