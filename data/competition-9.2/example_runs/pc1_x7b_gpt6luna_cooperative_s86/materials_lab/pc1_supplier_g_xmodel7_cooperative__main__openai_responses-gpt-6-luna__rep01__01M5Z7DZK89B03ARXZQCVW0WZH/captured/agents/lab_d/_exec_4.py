import pandas as pd
D=pd.read_csv('records.csv')
for p in ['p_9YW85TNK93','p_9YW85TNK95','p_9YW85TNK97']:
 z=D[D.prototype_id==p]
 print('\n',p, z.groupby('test').value.mean().to_dict())
 for t,g in z.groupby('test'):
  print(t, g.record_id.tolist())
