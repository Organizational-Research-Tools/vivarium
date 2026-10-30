import pandas as pd
df = pd.read_csv('records.csv')
d = df[(df['kind']=='qualification')&(df['project']=='QP-2342')]
g = d.groupby(['prototype_id','test']).value.mean().unstack()
print(g.to_string())
print()
d = df[(df['kind']=='qualification')&(df['project']=='QP-1466')]
print(d.groupby(['prototype_id','test']).value.mean().unstack().to_string())
