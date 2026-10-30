import pandas as pd
r=pd.read_csv('records.csv')
q=r[r.kind.eq('qualification')]
means=q.groupby(['project','prototype_id','test','instrument']).value.mean().unstack('test')
for p in ['QP-9259','QP-5174','QP-9980','QP-6879','QP-3617','QP-9273','QP-9219','QP-7092']:
 print('\n',p)
 x=means.loc[p] if p in means.index.get_level_values(0) else None
 if x is None: continue
 x=x.copy(); x['minnorm'] = ((x.get('seal hold temperature, °C',0)-78.625)/.25).combine(((x.get('edge crush resistance, kN/m',0)-7.235)/.03),min).combine(((x.get('wet strength retained, %',0)-79.8)/.4),min)
 print(x.sort_values('minnorm',ascending=False).head(12).to_string())
