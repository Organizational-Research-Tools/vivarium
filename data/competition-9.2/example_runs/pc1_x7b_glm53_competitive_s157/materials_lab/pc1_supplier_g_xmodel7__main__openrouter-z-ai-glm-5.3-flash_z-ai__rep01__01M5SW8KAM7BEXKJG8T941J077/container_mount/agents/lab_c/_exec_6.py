import pandas as pd
df = pd.read_csv('records.csv')
print(df.columns.tolist())
# find rows mentioning 99X / TWM
m = df[df.astype(str).apply(lambda r: r.str.contains('99X|TWM', na=False).any(), axis=1)]
print(m.to_string()[:4000])
