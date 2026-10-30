
import pandas as pd
df = pd.read_csv('records.csv')
print("Columns:", df.columns.tolist())
print()
# Look for p_8NVJHKV1KY
mask = df['prototype_id'].isin(['p_8NVJHKV1KT','p_8NVJHKV1KW','p_8NVJHKV1KY','p_8NVJHKV1M0'])
sub = df[mask].drop_duplicates(subset=['prototype_id'])
print(sub.to_string())
