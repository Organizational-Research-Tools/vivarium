import pandas as pd
x=pd.read_csv('records.csv');
print(x.groupby(['project','prototype_id','instrument']).agg(n=('value','size'),mean=('value','mean'),recipe=('base_sheet',lambda s:'')).to_string())
