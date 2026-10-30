import pandas as pd
r=pd.read_csv('records.csv')
# means of qualification panels by prototype/test
p=r[r.kind.str.lower().eq('qualification')].groupby(['project','prototype_id','test','measured_by']).value.mean().unstack('test')
print(p[p.water.notna() & (p.water>=79.8)].sort_values('water',ascending=False).to_string())
