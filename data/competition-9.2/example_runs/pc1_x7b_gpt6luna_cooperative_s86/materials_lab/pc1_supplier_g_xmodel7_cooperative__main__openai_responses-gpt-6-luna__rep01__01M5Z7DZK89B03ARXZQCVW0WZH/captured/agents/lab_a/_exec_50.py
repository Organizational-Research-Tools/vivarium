import pandas as pd
x=pd.read_csv('records.csv')
q=x[x.kind.eq('qualification')].groupby(['project','prototype_id','test']).agg(n=('value','count'),mean=('value','mean')).reset_index()
p=q.pivot_table(index=['project','prototype_id'],columns='test',values=['n','mean'],aggfunc='first')
# display candidates with all three panels, pass C thresholds
for (proj,pid),row in p.iterrows():
    if all(row.get(('n',t),0)==6 for t in ['seal hold temperature','edge crush resistance','wet strength retained']):
      m=[row.get(('mean',t),0) for t in ['seal hold temperature','edge crush resistance','wet strength retained']]
      if proj in ['QP-9259','QP-5174','QP-9980','QP-6879','QP-3617','QP-9273']:
       print(proj,pid, [round(float(v),5) for v in m])
