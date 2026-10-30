import pandas as pd
x=pd.read_csv('records.csv')
print(x.shape); print(x.columns.tolist())
print(x.head().to_string())