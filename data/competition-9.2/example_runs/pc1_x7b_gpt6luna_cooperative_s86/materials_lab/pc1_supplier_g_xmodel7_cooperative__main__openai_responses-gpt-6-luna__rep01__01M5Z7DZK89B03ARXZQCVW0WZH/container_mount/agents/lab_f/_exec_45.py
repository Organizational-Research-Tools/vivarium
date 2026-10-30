import pandas as pd
x=pd.read_csv('records.csv'); means=x.groupby(['project','prototype_id','test']).value.mean().unstack(); T={'seal hold temperature':78.625,'edge crush resistance':7.235,'wet strength retained':79.8};
for project in sorted(means.index.get_level_values(0).unique()):
 d=means.loc[project].copy();
 d['npass']=sum(d[t]>=v for t,v in T.items())
 d['nobs']=sum(d[t].notna() for t in T)
 # print all with >=2 data or any passes
 cand=d[(d.npass>=1)&(d.nobs>=2)].sort_values(['npass','nobs'],ascending=False)
 if len(cand): print('\n'+project+'\n'+cand.to_string())