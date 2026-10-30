import pandas as pd
x=pd.read_csv('records.csv')
print(x.shape); print(x.columns.tolist())
print(x.tail(5).to_string(index=False))