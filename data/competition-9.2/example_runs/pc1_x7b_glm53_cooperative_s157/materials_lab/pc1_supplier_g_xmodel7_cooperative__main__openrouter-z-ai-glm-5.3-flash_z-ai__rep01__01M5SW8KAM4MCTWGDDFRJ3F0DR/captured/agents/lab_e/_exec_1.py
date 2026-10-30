import pandas as pd
df = pd.read_csv('records.csv')
for pid in ['VE5','VE7','VE9','C0R','C0T','C0W','C0Y','C10']:
    m = df[df['prototype_id'].str.contains(pid, na=False)]
    print(pid, m[['prototype_id','project','test','value_kN_m' if False else df.columns[-1]]].to_string() if len(m) else 'no rows')