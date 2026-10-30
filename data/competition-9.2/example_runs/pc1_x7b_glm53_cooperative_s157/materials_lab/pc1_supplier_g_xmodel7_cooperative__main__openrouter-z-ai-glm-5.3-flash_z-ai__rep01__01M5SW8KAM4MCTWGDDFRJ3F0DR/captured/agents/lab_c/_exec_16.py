import pandas as pd
df=pd.read_csv('records.csv')
prot=sorted(set(df['prototype_id'].dropna()))
print(len(prot))
print([p for p in prot if p not in df[df.get('measured_by')=='lab_c']['prototype_id'].unique()][:80])
# just print those starting p_ not previously known? print all new-ish: filter for ones with project 2236/3068
print(df[df['project_id'].isin(['QP-2236','QP-3068'])][['prototype_id','project_id']].drop_duplicates().to_string())
