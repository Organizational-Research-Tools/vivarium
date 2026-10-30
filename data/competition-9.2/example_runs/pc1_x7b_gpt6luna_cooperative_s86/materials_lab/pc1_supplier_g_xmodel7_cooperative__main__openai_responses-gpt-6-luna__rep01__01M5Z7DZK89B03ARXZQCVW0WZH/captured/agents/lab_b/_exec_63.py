import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.kind=='qualification']; g=q.groupby(['project','prototype_id','test']).value.agg(['count','mean']).reset_index(); w=g.pivot(index=['project','prototype_id'],columns='test',values='mean').reset_index();
for c in ['edge crush resistance','seal hold temperature','wet strength retained']:
 w[c]=pd.to_numeric(w[c],errors='coerce')
w['base_sheet']=w.prototype_id.map(q.drop_duplicates('prototype_id').set_index('prototype_id').base_sheet)
# use means + print viable complete H and S pass, then water
for proj in ['QP-9259','QP-5174','QP-9980','QP-9219','QP-7092','QP-6879','QP-3617','QP-9273']:
 z=w[(w.project==proj)&(w['edge crush resistance']>=7.235)&(w['seal hold temperature']>=78.625)&(w['wet strength retained']>=79.8)]
 print('\n',proj,len(z)); print(z[['prototype_id','base_sheet','seal hold temperature','edge crush resistance','wet strength retained']].to_string(index=False))
# check H/S pass independent water
z=w[(w['edge crush resistance']>=7.235)&(w['seal hold temperature']>=78.625)]
print('\nall HS',z[['project','prototype_id','base_sheet','seal hold temperature','edge crush resistance','wet strength retained']].to_string(index=False))