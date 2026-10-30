import pandas as pd
x=pd.read_csv('records.csv'); ids=x[(x.project=='QP-9259') & (x.prototype_id.isin(['p_05Y71X58Q0','p_RR98QQY9EX','p_9YRC4C1K53']))].groupby(['prototype_id','instrument']).record_id.apply(list)
for k,v in ids.items(): print(k, v)
