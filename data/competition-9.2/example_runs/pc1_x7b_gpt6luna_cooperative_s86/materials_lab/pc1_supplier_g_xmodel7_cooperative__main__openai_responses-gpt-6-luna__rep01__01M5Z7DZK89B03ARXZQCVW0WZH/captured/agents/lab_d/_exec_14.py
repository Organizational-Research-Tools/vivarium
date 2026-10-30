import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_KBABVTJCWW','p_KBABVTJCX0']:
 d=x[(x.prototype_id==p)&(x.kind=='qualification')]
 print('\n',p)
 for test,g in d.groupby('test'):
  print(test, g.value.mean(), g.record_id.tolist())