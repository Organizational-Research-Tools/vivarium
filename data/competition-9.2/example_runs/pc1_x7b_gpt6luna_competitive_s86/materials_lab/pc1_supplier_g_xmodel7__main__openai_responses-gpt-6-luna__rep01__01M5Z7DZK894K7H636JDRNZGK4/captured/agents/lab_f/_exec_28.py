import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x.tail(35).to_string(index=False))