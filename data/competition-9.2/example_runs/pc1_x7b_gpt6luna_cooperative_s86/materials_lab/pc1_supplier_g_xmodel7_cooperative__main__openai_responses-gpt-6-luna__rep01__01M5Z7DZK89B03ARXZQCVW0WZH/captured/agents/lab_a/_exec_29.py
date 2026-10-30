import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x.get('prototype_id',pd.Series(dtype=str)).astype(str).str.startswith(('p_ZDY','p_EZR','p_B7'))].to_string(index=False)[:12000])