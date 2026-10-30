import pandas as pd, os
p='records.csv'
df=pd.read_csv(p)
print(df.shape); print(df.columns.tolist()); print(df.head().to_string(index=False))