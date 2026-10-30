import pandas as pd
df = pd.read_csv('records.csv')
print(df.columns.tolist())
print(df.tail(3))