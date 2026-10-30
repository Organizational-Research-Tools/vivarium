import pandas as pd
r=pd.read_csv('records.csv'); q=r[r.kind.eq('qualification')]
p=q.groupby(['project','prototype_id','test']).value.mean().unstack('test')
p.columns=['S' if x=='edge crush resistance' else 'H' if x=='seal hold temperature' else 'W' for x in p.columns]
for proj in ['QP-9259','QP-3617','QP-6879','QP-9980']:
 print('\n##',proj)
 x=p.loc[proj].copy()
 for c in ['H','S','W']:
  if c not in x: x[c]=float('nan')
 x['passesN']=x[['H','S','W']].notna().sum(axis=1)
 print(x.sort_values(['H','S','W'],ascending=False).to_string())
