import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x['prototype_id'].astype(str).str.startswith('p_YBRQHA8K')].to_string(index=False)[:15000])