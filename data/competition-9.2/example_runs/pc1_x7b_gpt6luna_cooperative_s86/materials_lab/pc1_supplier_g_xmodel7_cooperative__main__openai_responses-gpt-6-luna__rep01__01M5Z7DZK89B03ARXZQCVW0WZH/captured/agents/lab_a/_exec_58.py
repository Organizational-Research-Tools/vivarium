import pandas as pd
x=pd.read_csv('records.csv');x['value']=pd.to_numeric(x.value,errors='coerce');g=x[x.kind=='qualification'].groupby(['project','prototype_id','test']).value.mean().unstack()
for p in ['QP-9259','QP-5174','QP-9980','QP-9219','QP-7092','QP-6879','QP-3617','QP-9273']:
 if p not in g.index.get_level_values(0):continue
 z=g.loc[p]; z=z[(z['seal hold temperature']>=78.625)&(z['wet strength retained']>=79.8)]
 print('\n',p,'H&W',len(z)); print(z[['seal hold temperature','edge crush resistance','wet strength retained']].sort_values('edge crush resistance',ascending=False).head(10).to_string())