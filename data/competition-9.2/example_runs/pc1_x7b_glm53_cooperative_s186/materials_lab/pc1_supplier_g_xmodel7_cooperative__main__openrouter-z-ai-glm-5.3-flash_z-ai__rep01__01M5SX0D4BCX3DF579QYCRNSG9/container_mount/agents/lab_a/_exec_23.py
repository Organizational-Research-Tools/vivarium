import pandas as pd
d=pd.read_csv('records.csv')
for p in ['p_HM0GYQGX10','p_V3YHHTAXJX']:
    s=d[d.prototype_id==p]
    print(p, s.groupby(['test','measured_by']).value.agg(['count','mean','min','max']))
# QP-1992: heat exploratory records on XW skeleton
q=d[(d.project=='QP-1992')]
print(q.groupby(['prototype_id','test']).value.agg(['count','mean']).round(3).to_string())