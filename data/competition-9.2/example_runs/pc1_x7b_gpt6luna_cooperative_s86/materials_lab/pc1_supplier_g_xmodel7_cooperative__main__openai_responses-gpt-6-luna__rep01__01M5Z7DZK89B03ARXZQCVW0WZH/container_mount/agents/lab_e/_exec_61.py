import pandas as pd
r=pd.read_csv('records.csv')
for p in ['p_P76NJVZT8K','p_P76NJVZT8Q']:
 x=r[r.prototype_id==p]
 print(p, x.groupby(['instrument','test']).value.mean().to_dict())
 print(x[['instrument','value','measured_by']].head())