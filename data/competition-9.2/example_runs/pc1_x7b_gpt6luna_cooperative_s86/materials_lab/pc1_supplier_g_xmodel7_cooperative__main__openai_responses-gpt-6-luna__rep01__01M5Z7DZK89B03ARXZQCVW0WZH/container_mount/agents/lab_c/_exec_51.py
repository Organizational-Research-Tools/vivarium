import pandas as pd
r=pd.read_csv('records.csv');
ps=['p_Q3WNAPKP69','p_Q3WNAPKP6B','p_Q3WNAPKP6D','p_P76NJVZT8F','p_P76NJVZT8H','p_P76NJVZT8Q','p_7S32NDTXBQ','p_7S32NDTXBS','p_7S32NDTXBV']
for p in ps:
 d=r[r.prototype_id.eq(p)]
 if len(d): print('\n',p,d.groupby(['test','measured_by']).value.mean().round(4).to_dict())
