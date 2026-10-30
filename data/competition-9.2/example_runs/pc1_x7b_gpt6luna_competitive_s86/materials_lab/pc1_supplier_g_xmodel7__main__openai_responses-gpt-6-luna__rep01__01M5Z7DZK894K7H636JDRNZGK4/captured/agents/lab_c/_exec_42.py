import pandas as pd
x=pd.read_csv('records.csv'); print(x.columns.tolist());
for p in ['p_6HZQR01SM9','p_6HZQR01SMH','p_6HZQR01SMB']:
 z=x[x.prototype_id==p]; print('\n',p,len(z)); print(z.to_string(index=False))