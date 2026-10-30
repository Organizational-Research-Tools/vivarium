
import pandas as pd
df = pd.read_csv('records.csv')
print(f"Total rows: {len(df)}")
print(f"Test values: {df['test'].unique()}")
print(f"Kind values: {df['kind'].unique()}")
print(f"\nSample rows:")
print(df.head(10).to_string())
print(f"\nValue stats: min={df['value'].min()}, max={df['value'].max()}")
print(f"\nTests breakdown:\n{df['test'].value_counts()}")
print(f"\nKind breakdown:\n{df['kind'].value_counts()}")
