import pandas as pd
df = pd.read_csv('records.csv')
print(df.columns.tolist())
print(df.head(3))
print(df.shape)
