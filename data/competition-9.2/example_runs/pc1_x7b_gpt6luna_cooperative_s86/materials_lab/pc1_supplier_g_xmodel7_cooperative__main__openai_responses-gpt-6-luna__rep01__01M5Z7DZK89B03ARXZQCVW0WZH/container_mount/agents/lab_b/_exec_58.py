import pandas as pd
x=pd.read_csv('records.csv')
q=x[x.kind=='qualification']
means=q.groupby(['project','prototype_id','instrument','test','measured_by']).agg(mean=('value','mean'),n=('value','size')).reset_index()
w=means.pivot_table(index=['project','prototype_id'],columns='test',values='mean')
n=q.groupby(['project','prototype_id','instrument']).size().unstack(fill_value=0)
# map instrument to test; display any each test six panels and all C pass
for col in ['seal hold temperature','edge crush resistance','wet strength retained']:
    pass
print('columns', list(w.columns))
# group panels coverage
coverage=q.groupby(['project','prototype_id','instrument']).size().unstack(fill_value=0)
print('\nAll three panel candidates with C passes:')
for (pr,pid),r in w.iterrows():
    # only show available panels exactly six per instrument, but note aliases not same ID? yes
    tests=q[q.project.eq(pr)&q.prototype_id.eq(pid)].groupby('instrument').size().to_dict()
    if all(tests.get(i,0)==6 for i in ['heat','strength','water']):
       vals=[r.get('seal hold temperature'),r.get('edge crush resistance'),r.get('wet strength retained')]
       if vals[0]>=78.625 and vals[1]>=7.235 and vals[2]>=79.8: print(pr,pid,vals)
print('\nNear complete candidates rev C:')
for (pr,pid),r in w.iterrows():
    vals=[r.get('seal hold temperature'),r.get('edge crush resistance'),r.get('wet strength retained')]
    tests=q[q.project.eq(pr)&q.prototype_id.eq(pid)].groupby('instrument').size().to_dict()
    if any(pd.notna(v) for v in vals) and (pr in ['QP-9259','QP-3617','QP-6879','QP-9980']):
      print(pr,pid,' '.join(f'{v:.5f}' if pd.notna(v) else '-' for v in vals),tests)
