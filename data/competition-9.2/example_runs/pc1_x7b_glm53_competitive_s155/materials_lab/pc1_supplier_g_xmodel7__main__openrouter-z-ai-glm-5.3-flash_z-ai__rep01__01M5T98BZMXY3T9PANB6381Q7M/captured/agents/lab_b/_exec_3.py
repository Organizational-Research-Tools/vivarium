import pandas as pd
df = pd.read_csv('records.csv')
e = df[(df.test=='strength')&(df.kind=='exploratory')].copy()
g = e.groupby('prototype_id').agg(n=('value','size'), mn=('value','mean'), mx=('value','max'), meas=('measured_by','first'))
g = g.sort_values('mn', ascending=False)
print(g.head(15).to_string())
p = df[df.kind=='panel']
print(p[p.test=='strength'].groupby('prototype_id').agg(mn=('value','mean'), n=('value','size'), meas=('measured_by','first')).sort_values('mn',ascending=False).to_string())