import pandas as pd
r=pd.read_csv('records.csv')
print(r.columns.tolist()); print(r.shape); print(r.head().to_string())