import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist()); print(x.shape)
print(x.tail(10).to_string(index=False))