import pandas as pd
x=pd.read_csv('records.csv')
print(x[x.kind.eq('qualification')].groupby(['project','prototype_id','test','instrument']).agg(n=('value','count'),mean=('value','mean')).reset_index().to_string(index=False))