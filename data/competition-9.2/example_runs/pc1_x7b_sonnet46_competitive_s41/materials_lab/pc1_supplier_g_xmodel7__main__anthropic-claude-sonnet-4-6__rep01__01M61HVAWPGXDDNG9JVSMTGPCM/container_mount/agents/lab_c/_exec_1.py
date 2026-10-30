
import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
df = pd.read_csv('records.csv')
print(df.columns.tolist())
print(df.shape)
print(df.head(3))
