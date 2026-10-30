
import pandas as pd

df = pd.read_csv('records.csv')
print("Columns:", df.columns.tolist())
print(f"Total rows: {len(df)}")
print(df.dtypes)
