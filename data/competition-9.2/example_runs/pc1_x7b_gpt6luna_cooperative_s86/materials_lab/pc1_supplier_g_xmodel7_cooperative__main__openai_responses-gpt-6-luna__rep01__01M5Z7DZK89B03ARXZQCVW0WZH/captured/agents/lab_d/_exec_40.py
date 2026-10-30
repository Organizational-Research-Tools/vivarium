import pandas as pd
x=pd.read_csv('records.csv');
for pr in ['QP-9259','QP-9980','QP-5174','QP-9219','QP-7092','QP-6879','QP-3617','QP-9273']:
 print('\n',pr)
 y=x[x.project==pr]
 for p,g in y.groupby('prototype_id'):
  v=g.groupby('test').value.mean()
  if len(v)>=2:
   print(p, ' '.join(f'{k[:2]}={z:.4f}' for k,z in v.items()), 'kinds',','.join(g.kind.unique()))