import pandas as pd
df = pd.read_csv('records.csv')
print(df.shape)
for pat in ['8FVK7A1FX','MHYGPBWR1V','rep_2LCT']:
    m = df[df.astype(str).apply(lambda row: row.str.contains(pat, na=False).any(), axis=1)]
    print(pat, len(m))
    if len(m): print(m.to_string())
print(df.columns.tolist())
print(df[df['project'].astype(str).str.contains('3068', na=False)]['test'].value_counts() if 'project' in df.columns else '')