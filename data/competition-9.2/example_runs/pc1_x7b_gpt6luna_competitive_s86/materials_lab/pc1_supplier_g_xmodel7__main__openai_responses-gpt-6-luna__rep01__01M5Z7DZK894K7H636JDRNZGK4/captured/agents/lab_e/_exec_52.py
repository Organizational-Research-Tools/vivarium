import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[(x.prototype_id=='p_7S365TH6Y2')][['record_id','value','kind','instrument','measured_by']].to_string(index=False))