import pandas as pd
x=pd.read_csv('records.csv');
for p in ['p_NQYNDKZ3C8','p_NQYNDKZ3CA','p_NQYNDKZ3CC','p_NQYNDKZ3CE','p_NQYNDKZ3CG','p_NQYNDKZ3CJ']:
 z=x[(x.prototype_id==p)&(x.test=='wet strength retained')]; print(p,round(z.value.mean(),4),len(z))