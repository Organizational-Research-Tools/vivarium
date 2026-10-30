import pandas as pd
x=pd.read_csv('records.csv'); x=x[x.kind=='qualification']; g=x.groupby(['project','prototype_id','test']).value.agg(['mean','count']).reset_index(); p=g.pivot(index=['project','prototype_id'],columns='test',values='mean'); n=g.pivot(index=['project','prototype_id'],columns='test',values='count'); print('complete candidates passing revC:'); thresholds={'seal hold temperature':78.625,'edge crush resistance':7.235,'wet strength retained':79.8}; cols=list(thresholds); good=[]
for idx,row in p.iterrows():
 if all(n.loc[idx,c]==6 for c in cols) and all(row[c]>=thresholds[c] for c in cols): good.append((idx,row.to_dict()))
print(good)
print('\nHeat+water passed candidates needing strength:')
for idx,row in p.iterrows():
 if n.loc[idx].get('seal hold temperature',0)==6 and n.loc[idx].get('wet strength retained',0)==6 and row.get('seal hold temperature',0)>=78.625 and row.get('wet strength retained',0)>=79.8:
  print(idx, row.to_dict(), 'strength', n.loc[idx].get('edge crush resistance',0))