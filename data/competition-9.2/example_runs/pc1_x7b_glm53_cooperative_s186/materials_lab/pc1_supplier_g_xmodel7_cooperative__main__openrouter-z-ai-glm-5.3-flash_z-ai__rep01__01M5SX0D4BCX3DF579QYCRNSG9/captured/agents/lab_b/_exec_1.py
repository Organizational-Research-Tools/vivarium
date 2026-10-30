import pandas as pd
df = pd.read_csv('records.csv')
print(df.columns.tolist())
print(len(df))
print(df['project_id'].value_counts())
print(df['property'].value_counts())