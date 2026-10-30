import pandas as pd
r=pd.read_csv('records.csv'); x=r[r.kind.eq('qualification')].groupby(['project','prototype_id','test']).value.mean().unstack('test').reset_index();
print(x[(x['seal hold temperature']>=78.625)&(x['edge crush resistance']>=7.235)].to_string(index=False))