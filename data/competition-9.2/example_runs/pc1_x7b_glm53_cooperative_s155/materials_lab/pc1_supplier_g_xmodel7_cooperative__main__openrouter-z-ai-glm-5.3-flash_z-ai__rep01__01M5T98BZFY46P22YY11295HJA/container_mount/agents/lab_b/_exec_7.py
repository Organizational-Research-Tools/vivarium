import pandas as pd
df = pd.read_csv('records.csv')
print(df.columns.tolist())
print(len(df))
# find exploratory readings per prototype with strength values
s = df[df['property']=='strength'] if 'property' in df.columns else None
print(df.head(20).to_string())
