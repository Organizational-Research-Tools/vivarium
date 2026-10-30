import pandas as pd
r=pd.read_csv('records.csv'); print(r.columns.tolist());
for p in ['p_Z398MDW5ST','p_5WCK5KFXKY']:
 d=r[r.prototype_id.eq(p)]
 print('\n',p,'rows',len(d)); print(d.to_string(index=False))