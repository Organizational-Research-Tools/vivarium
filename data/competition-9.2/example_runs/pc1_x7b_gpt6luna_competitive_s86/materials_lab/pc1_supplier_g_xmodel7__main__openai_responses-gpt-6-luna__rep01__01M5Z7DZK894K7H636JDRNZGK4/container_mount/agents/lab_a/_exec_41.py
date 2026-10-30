import pandas as pd
x=pd.read_csv('records.csv')
# filter non-H8Z
x=x[x.base_sheet!='H8Z']
agg=x.groupby(['project','prototype_id','test','kind']).value.agg(['mean','count']).reset_index()
for proj in x.project.dropna().unique():
    print('\n',proj)
    sub=agg[agg.project==proj]
    # summarize each proto latest qualification means if present else exploratory mean, instruments property tests
    for pid,g in sub.groupby('prototype_id'):
      vals={}
      for t in ['seal hold temperature','edge crush resistance','wet strength retained']:
        h=g[g.test==t]
        if len(h):
          # qualification preferred, otherwise max? all readings mean same fixed panels; exploratory mean helpful
          q=h[h.kind=='qualification']
          vals[t]= (q['mean'].iloc[-1] if len(q) else h['mean'].mean(), 'Q' if len(q) else 'E', int(q['count'].iloc[-1] if len(q) else h['count'].sum()))
      if len(vals)>=2:
        heat=vals.get('seal hold temperature',(0,'',0))[0]
        strength=vals.get('edge crush resistance',(0,'',0))[0]
        water=vals.get('wet strength retained',(0,'',0))[0]
        if heat>=78.5 or strength>=7.21 or water>=79.8:
          print(pid, vals)
