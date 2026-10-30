import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x.get('prototype_id',pd.Series(dtype=str)).eq('p_3TS98N4J3A')].to_string(index=False) if 'prototype_id' in x.columns else x.tail().to_string(index=False))