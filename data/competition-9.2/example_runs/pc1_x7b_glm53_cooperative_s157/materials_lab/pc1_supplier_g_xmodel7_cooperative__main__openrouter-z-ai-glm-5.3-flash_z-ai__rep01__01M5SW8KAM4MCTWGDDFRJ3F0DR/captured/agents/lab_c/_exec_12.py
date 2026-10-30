import pandas as pd
df=pd.read_csv('records.csv')
g=df[(df.prototype_id=='p_55NSKA6RFT')&(df.kind=='qualification')]
print(g[['record_id','instrument','test','specimen','value','measured_by']].to_string())
for t,x in g.groupby('test'): print(t, x.value.mean().round(3), x.measured_by.unique())
