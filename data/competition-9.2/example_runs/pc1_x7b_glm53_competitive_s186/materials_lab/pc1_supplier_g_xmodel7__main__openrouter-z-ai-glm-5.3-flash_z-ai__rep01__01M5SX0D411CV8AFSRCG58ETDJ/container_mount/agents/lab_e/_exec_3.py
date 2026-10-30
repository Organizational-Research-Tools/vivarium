import pandas as pd
df = pd.read_csv('records.csv')
print(df.shape); print(df.tail(5).to_string())