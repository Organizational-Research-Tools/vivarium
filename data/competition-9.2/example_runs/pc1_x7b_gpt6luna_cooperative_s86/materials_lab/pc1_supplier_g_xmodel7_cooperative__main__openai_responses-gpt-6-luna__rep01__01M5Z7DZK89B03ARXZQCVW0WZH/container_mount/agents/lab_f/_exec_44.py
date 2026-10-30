import pandas as pd
x=pd.read_csv('records.csv'); means=x.groupby(['project','prototype_id','test']).value.mean().unstack();
threshold={'seal hold temperature':78.625,'edge crush resistance':7.235,'wet strength retained':79.8}
for proj,g in means.groupby(level=0):
    pass
# count pass tests
for p in sorted(means.index.get_level_values(0).unique()):
 d=means.loc[p].copy();
 for t,v in threshold.items():
  if t not in d: d[t]=float('nan')
 d['npass'] = sum(d[t]>=v for t,v in threshold.items())
 d=d[d.npass>=2]
 if len(d):
  print('\n',p);print(d.sort_values('npass',ascending=False).to_string())