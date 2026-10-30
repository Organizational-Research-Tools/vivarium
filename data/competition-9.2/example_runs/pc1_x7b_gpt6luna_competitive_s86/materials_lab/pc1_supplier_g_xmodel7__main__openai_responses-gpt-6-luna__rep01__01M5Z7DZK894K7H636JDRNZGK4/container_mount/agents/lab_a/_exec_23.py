import pandas as pd
x=pd.read_csv('records.csv'); cols=[c for c in x.columns if c not in ['record_id','kind','project','prototype_id','instrument','test','specimen','value','unit','measured_by','requester']]
for p in ['p_H6M64FVH6S','p_H6M64FVH6V','p_H6M64FVH7B','p_W3C23XARDY','p_W3B2SY0Z6A']:
 z=x[x.prototype_id==p]; print('\n',p); print(z[cols].drop_duplicates().to_string(index=False))