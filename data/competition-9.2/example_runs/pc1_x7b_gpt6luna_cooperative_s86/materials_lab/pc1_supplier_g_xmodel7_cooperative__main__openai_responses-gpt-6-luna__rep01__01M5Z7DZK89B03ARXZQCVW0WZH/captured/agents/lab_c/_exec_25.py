import pandas as pd
r=pd.read_csv('records.csv')
print(r.shape)
print(r.columns.tolist())
print(r.tail(5).to_string(index=False))