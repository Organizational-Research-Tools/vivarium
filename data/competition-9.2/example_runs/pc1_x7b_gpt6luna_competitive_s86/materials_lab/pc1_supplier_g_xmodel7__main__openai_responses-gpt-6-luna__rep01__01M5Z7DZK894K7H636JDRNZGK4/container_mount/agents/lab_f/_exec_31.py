import pandas as pd
x=pd.read_csv('records.csv')
print(x.shape)
print(x.columns.tolist())
print(x[x.prototype_id.astype(str).str.contains('KCVBREJ1G|AZKMFQD4V')].to_string(index=False))