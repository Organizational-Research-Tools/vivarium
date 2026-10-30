import pandas as pd
x=pd.read_csv('records.csv'); d=x[x.prototype_id=='p_YJCA9TYHK1']; print(d[['record_id','kind','test','value','measured_by']].to_string(index=False))