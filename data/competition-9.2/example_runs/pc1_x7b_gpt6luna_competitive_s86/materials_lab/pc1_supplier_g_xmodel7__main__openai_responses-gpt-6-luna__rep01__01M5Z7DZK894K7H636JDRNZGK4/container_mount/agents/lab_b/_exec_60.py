import pandas as pd
x=pd.read_csv('records.csv'); q=x[(x.kind=='qualification')].copy(); g=q.groupby(['project','prototype_id','test']).agg(mean=('value','mean'),n=('value','count'),by=('measured_by','first')).reset_index(); print(g[g.test=='edge crush resistance'].sort_values('mean',ascending=False).head(30).to_string(index=False));
# joined all test means for qualified panel candidates
p=g.pivot(index=['project','prototype_id'],columns='test',values='mean'); print('\nAll passing C any full panels'); print(p[(p['edge crush resistance']>=7.235)&(p['seal hold temperature']>=78.625)&(p['wet strength retained']>=79.8)].to_string())
