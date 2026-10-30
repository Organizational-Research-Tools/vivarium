import pandas as pd
df=pd.read_csv("records.csv")
q=df[(df.kind=='qualification')&(df.test=='edge crush resistance')]
print(q[['record_id','prototype_id','measured_by','requester','value','specimen']].to_string())