import pandas as pd, numpy as np
x=pd.read_csv('records.csv')
# summary all proto test mean & kind
agg=x.groupby(['project','prototype_id','test','kind']).value.agg(['mean','count']).reset_index()
print('Candidate heat exploratory means >=78.15, grouped')
h=agg[(agg.test=='heat')&(agg.kind=='exploratory')&(agg['mean']>=78.15)].sort_values('mean',ascending=False)
print(h.to_string(index=False))
print('\nPass candidate full panel values all properties')
p=x[x.kind=='qualification'].groupby(['project','prototype_id','test']).value.mean().unstack()
print(p[(p.heat>=78.25)&(p.strength>=7.19)&(p['water']>=79.2)].to_string())
print('\nall panel data means projects candidates')
print(p[(p.heat>=78.15)&(p.strength>=7.15)&(p['water']>=79)].sort_values('heat',ascending=False).to_string())