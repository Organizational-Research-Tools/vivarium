import pandas as pd
r=pd.read_csv('records.csv')
print(r.shape)
print(r.columns.tolist())
print(r.head(2).to_string(index=False))