import pandas as pd
df = pd.read_csv('records.csv')
# composition is unknown for granted ones, so find prototype ids by suffix
ids = [p for p in df.prototype_id.unique() if isinstance(p,str) and p.endswith('99X') or (isinstance(p,str) and p.endswith('TWM'))]
print(ids)
print(df[df.prototype_id.isin(ids)].head(30).to_string())
