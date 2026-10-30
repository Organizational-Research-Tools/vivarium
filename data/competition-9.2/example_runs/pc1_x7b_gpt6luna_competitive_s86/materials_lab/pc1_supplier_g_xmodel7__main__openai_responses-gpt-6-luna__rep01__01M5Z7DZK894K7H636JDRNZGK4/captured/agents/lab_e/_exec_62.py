import pandas as pd
x=pd.read_csv('records.csv')
for pid in ['p_H6M64FVH6V','p_H6M64FVH7B']:
 g=x[x.prototype_id==pid]
 print('\n',pid, g[['record_id','instrument','kind','value','owner','sample']].to_string(index=False))
