import pandas as pd
x=pd.read_csv('records.csv')
g=x.groupby(['project','prototype_id','kind','test'],dropna=False).agg(mean=('value','mean'),n=('value','count'),owner=('measured_by',lambda s:','.join(sorted(set(s)))))
print(g.to_string())
