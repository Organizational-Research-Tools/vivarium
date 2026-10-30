import pandas as pd
r=pd.read_csv('records.csv'); ids=['p_P76NJVZT8K','p_P76NJVZT8Q'];
for p in ids:
 x=r[(r.prototype_id==p)&(r.kind=='qualification')]; print(p); print(x.groupby('test').value.agg(['mean','count']))