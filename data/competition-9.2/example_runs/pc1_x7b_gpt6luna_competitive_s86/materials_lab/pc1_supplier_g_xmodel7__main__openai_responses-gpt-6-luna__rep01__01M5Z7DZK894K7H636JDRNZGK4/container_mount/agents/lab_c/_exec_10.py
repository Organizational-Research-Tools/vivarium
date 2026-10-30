import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x.tail(30).to_string(index=False))
