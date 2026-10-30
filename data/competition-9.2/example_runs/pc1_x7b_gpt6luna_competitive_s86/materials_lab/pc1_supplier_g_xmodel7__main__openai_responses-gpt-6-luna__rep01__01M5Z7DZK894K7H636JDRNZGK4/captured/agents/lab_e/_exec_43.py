import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x.prototype_id.astype(str).str.contains('W3C23XARE[68GR]')].to_string(index=False))