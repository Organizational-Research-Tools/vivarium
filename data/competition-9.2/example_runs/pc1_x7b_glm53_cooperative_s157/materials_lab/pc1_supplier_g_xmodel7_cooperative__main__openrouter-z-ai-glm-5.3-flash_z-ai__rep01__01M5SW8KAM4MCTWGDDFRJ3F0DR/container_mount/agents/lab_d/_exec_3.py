import pandas as pd
df=pd.read_csv("records.csv")
print(df.shape); print(df.columns.tolist()); print(df.head())
print(df['instrument'].value_counts() if 'instrument' in df else '')