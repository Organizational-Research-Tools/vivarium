import pandas as pd
df = pd.read_csv("records.csv")
print(df.shape); print(df.columns.tolist()); print(df.head(20).to_string())