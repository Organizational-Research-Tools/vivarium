import pandas as pd
x=pd.read_csv('records.csv'); print(x[x.prototype_id=='p_8ATRDK3V3Z'][['record_id','instrument','value','measured_by']].to_string(index=False)); print(x.project.value_counts())