import pandas as pd
r=pd.read_csv('records.csv')
for pid in ['p_3SZ9SPMFY6','p_62M20S6MVN']:
 print(pid, r[r.prototype_id==pid].to_string(index=False))
