import pandas as pd
D=pd.read_csv('records.csv')
p='p_NBE0SSEEDQ'
g=D[(D.prototype_id==p)&(D.kind=='qualification')].sort_values(['test','specimen'])
print(g[['record_id','test','specimen','value','measured_by','requester']].to_string(index=False))
print('\nmeans')
print(g.groupby(['test','measured_by']).value.mean())