import pandas as pd
x=pd.read_csv('records.csv')
# per proto averages, counts, test means on all projects; qualification/exploratory
for (pr,pid),g in x.groupby(['project','prototype_id']):
    q={}
    for t,h in g.groupby('test'):
        q[t]=(h.value.mean(),len(h),h.kind.iloc[0],set(h.measured_by))
    if pr in ['QP-8807','QP-7092','QP-9219','QP-6879','QP-3617','QP-9273','QP-5174']:
        s=q.get('edge crush resistance'); w=q.get('wet strength retained'); ht=q.get('seal hold temperature')
        if ((s and s[0]>=7.22) and (w and w[0]>=79.8)) or ((s and s[0]>=7.23) and (w and w[0]>=79.8)):
            print(pr,pid,'H',ht,'S',s,'W',w)
