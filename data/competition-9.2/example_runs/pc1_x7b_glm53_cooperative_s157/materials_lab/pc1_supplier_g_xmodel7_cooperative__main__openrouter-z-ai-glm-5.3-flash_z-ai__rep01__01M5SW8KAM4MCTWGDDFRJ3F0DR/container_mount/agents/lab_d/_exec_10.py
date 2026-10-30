import pandas as pd
df = pd.read_csv('records.csv')
# find rows for these prototypes
ids = ['p_QQZW86K9P0','p_QQZW86K9P2','p_QQZW86K9P8','p_CWYDQP98S8']
print(df[df.prototype_id.isin(ids)].to_string() if 'prototype_id' in df.columns else df.columns.tolist())