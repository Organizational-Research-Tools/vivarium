import pandas as pd
df=pd.read_csv('records.csv')
q=df[df.project=='QP-6489']
print(q[['record_id','prototype_id','instrument','test','value','measured_by']].to_string())
