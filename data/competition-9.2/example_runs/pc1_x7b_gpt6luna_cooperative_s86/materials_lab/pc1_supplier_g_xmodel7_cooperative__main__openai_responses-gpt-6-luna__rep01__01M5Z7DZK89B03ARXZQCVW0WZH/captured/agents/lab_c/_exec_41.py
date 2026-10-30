import pandas as pd
r=pd.read_csv('records.csv')
print(r.shape); print(r.columns.tolist()); print(r.tail().to_string(index=False))